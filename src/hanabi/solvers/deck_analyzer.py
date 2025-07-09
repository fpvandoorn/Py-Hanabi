import collections
import dataclasses
from enum import Enum
from typing import List, Any, Optional, Tuple, Set
from dataclasses import dataclass

import alive_progress

import hanabi.hanab_game
from hanabi import database
from hanabi import logger
from hanabi import hanab_game
from hanabi.hanab_game import DeckCard
from hanabi.live import compress

from hanabi.database import games_db_interface


class InfeasibilityType(Enum):
    Pace                   = 0  # value denotes the number of cards still left in the deck
    DoubleBottom2With5s    = 1  # same, special case for 2p
    TripleBottom1With5s    = 2  # same, special case for 2p
    HandSize               = 10  # idx denotes index of last card drawn before being forced to discard a crit
    PaceAfterSqueeze       = 11  # pace goes down to 0 after cards have been forcibly lost due to hand size that *might* have helped prevent this situation.
    BottomTopDeck          = 20  # Card distribution in a single suit in starting hands + near end of deck is impossible to win. value represents suit Index

    # further reasons, currently not scanned for
    DoubleBottomTopDeck    = 30  # Card distribution in two suits in starting hands + near end of deck is impossible to win.
    CritAtBottom           = 40

    # Default reason when we have nothing else
    SAT                    = 50
    Manual                 = 60


class InfeasibilityReason:
    def __init__(self, infeasibility_type: InfeasibilityType, value=None):
        self.type = infeasibility_type
        self.value = value

    def __repr__(self):
        match self.type:
            case InfeasibilityType.Pace:
                return "Out of Pace after drawing card {}".format(self.value)
            case InfeasibilityType.HandSize:
                return "Out of hand size after drawing card {}".format(self.value)
            case InfeasibilityType.CritAtBottom:
                return "Critical non-5 at bottom"
            case _:
                return "{} ({})".format(self.type, self.value)

    def __eq__(self, other):
        return self.type == other.type and self.value == other.value

    def __hash__(self):
        return (self.type, self.value).__hash__()


def generate_all_choices(l: List[List[Any]]):
    if len(l) == 0:
        yield []
        return
    head, *tail = l
    for option in head:
        for back in generate_all_choices(tail):
            yield [option] + back


# Returns index of the suit that makes deck infeasible, or None if it does not exist
def check_for_top_bottom_deck_loss(instance: hanab_game.HanabiInstance) -> Optional[int]:
    hands = [instance.deck[p * instance.hand_size : (p+1) * instance.hand_size] for p in range(instance.num_players)]

    # scan the deck in reverse order if any card is forced to be late
    found = {}
    # Note that only the last 4 cards are relevant for single-suit distribution loss
    for i, card in enumerate(reversed(instance.deck[-4:])):
        if card in found.keys():
            found[card] += 1
        else:
            found[card] = 1

        if found[card] >= 3 or (card.rank != 1 and found[card] >= 2):
            max_rank_starting_extra_round = card.rank + (instance.deck_size - card.deck_index - 2)

            # Next, need to figure out what positions of cards of the same suit are fixed
            positions_by_rank = [[] for _ in range(6)]
            for rank in range(max_rank_starting_extra_round, 6):
                for player, hand in enumerate(hands):
                    card_test = DeckCard(card.suitIndex, rank)
                    for card_hand in hand:
                        if card_test == card_hand:
                            positions_by_rank[rank].append(player)

            # clean up where we have free choice anyway
            for rank, positions in enumerate(positions_by_rank):
                if rank != 5 and len(positions) < 2:
                    positions.clear()
                if len(positions) == 0:
                    positions.append(None)

            # Now, iterate through all choices in starting hands (None stands for free choice of a card) and check them
            assignment_found = False
            for assignment in generate_all_choices(positions_by_rank):
                cur_player = None
                num_turns = 0
                for rank in range(max_rank_starting_extra_round, 6):
                    if cur_player is None or assignment[rank] is None:
                        num_turns += 1
                    else:
                        # Note the -1 and +1 to output things in range [1,5] instead of [0,4]
                        num_turns += (assignment[rank] - cur_player - 1) % instance.num_players + 1

                    if assignment[rank] is not None:
                        cur_player = assignment[rank]
                    elif cur_player is not None:
                        cur_player = (cur_player + 1) % instance.num_players

                if num_turns <= instance.num_players + 1:
                    assignment_found = True

            # If no assignment worked out, the deck is infeasible because of this suit
            if not assignment_found:
                return card.suitIndex

    # If we reach this point, we checked for every card near the bottom of the deck and found a possible endgame each
    return None


def analyze_2p_bottom_loss(instance: hanab_game.HanabiInstance) -> List[InfeasibilityReason]:
    reasons = []
    filtered_deck = [card for card in instance.deck if card.rank != 5]
    if instance.num_players == 2:
        if filtered_deck[-1] == filtered_deck[-2] and filtered_deck[-1].rank == 2:
            reasons.append(InfeasibilityReason(InfeasibilityType.Pace, filtered_deck[-2].deck_index - 1))
            reasons.append(InfeasibilityReason(InfeasibilityType.DoubleBottom2With5s, filtered_deck[-2].deck_index - 1))
        if filtered_deck[-1] == filtered_deck[-2] and filtered_deck[-2] == filtered_deck[-3] and filtered_deck[-3].rank == 1:
            reasons.append(InfeasibilityReason(InfeasibilityType.Pace, filtered_deck[-3].deck_index - 1))
            reasons.append(InfeasibilityReason(InfeasibilityType.TripleBottom1With5s, filtered_deck[-2].deck_index - 1))

    return reasons


@dataclass
class ValueWithIndex:
    value: int
    index: int
    stores_minimum: bool = True

    def update(self, value, index):
        if (self.stores_minimum and value < self.value) or (not self.stores_minimum and value > self.value):
            self.value = value
            self.index = index

    def __repr__(self):
        return "{} (at {})".format(self.value, self.index)

@dataclass
class AnalysisResult:
    infeasibility_reasons: List[InfeasibilityReason] = dataclasses.field(default_factory=lambda: [])
    min_pace: ValueWithIndex = dataclasses.field(default_factory=lambda: ValueWithIndex(100, 0, True))
    max_stored_crits: ValueWithIndex = dataclasses.field(default_factory=lambda: ValueWithIndex(0, 0, False))
    max_stored_cards: ValueWithIndex = dataclasses.field(default_factory=lambda: ValueWithIndex(0, 0, False))


def analyze_pace_and_hand_size(instance: hanab_game.HanabiInstance, do_squeeze: bool = True, list_all_pace_cuts: bool = False) -> AnalysisResult:
    reasons = AnalysisResult()
    # we will sweep through the deck and pretend that
    # - we keep all non-trash cards in our hands
    # - we instantly play all playable cards as soon as we have them
    # - we recurse on this instant-play
    #
    # For example, we assume that once we draw r2, we check if we can play r2.
    # If yes, then we also check if we drew r3 earlier and so on.
    # If not, then we keep r2 in our hands
    #
    # In total, this is equivalent to assuming that we have infinitely many clues
    # and infinite storage space in our hands (which is of course not true),
    # but even in this setting, some games are infeasible due to pace issues
    # that we can detect
    #
    # A small refinement is to pretend that we only have infinite storage for non-crit cards,
    # for crit-cards, the usual hand card limit applies.
    # This allows us to detect some seeds where there are simply too many unplayable cards to hold at some point
    # that also can't be discarded

    stacks = [0] * instance.num_suits

    # we will ensure that stored_crits is a subset of stored_cards
    stored_cards = set()
    stored_crits = set()

    pace_found = False
    hand_size_found = False
    squeeze = False
    artificial_crits = set()


    # Investigate BDRs. This catches special cases of Pace losses in 2p, as well as mark some cards critical because
    # their second copies cannot be used.
    filtered_deck = [card for card in instance.deck if card.rank != 5]
    if instance.num_players == 2:
        # In 2-player, the second-last card cannot be played if it is a 2
        if filtered_deck[-2].rank == 2:
            artificial_crits.add(filtered_deck[-2])

        # In 2-player, in case there is double bottom 3 of the same suit, the card immediately before cannot be played:
        # After playing that one and drawing the first 3, exactly 3,4,5 of the bottom suit have to be played
        if filtered_deck[-1] == filtered_deck[-2] and filtered_deck[-2].rank == 3:
            artificial_crits.add(filtered_deck[-3])
    elif instance.num_players == 3:
        if filtered_deck[-1] == filtered_deck[-2] and filtered_deck[-2].rank == 2:
            artificial_crits.add(filtered_deck[-3])

    # Last card in the deck can never be played unless it is a five.
    if instance.deck[-1].rank != 5:
        artificial_crits.add(instance.deck[-1])

    for (card_index, card) in enumerate(instance.deck):
        if card.rank == stacks[card.suitIndex] + 1:
            # card is playable
            stacks[card.suitIndex] += 1
            # check for further playables that we stored
            for check_rank in range(card.rank + 1, 6):
                check_card = hanab_game.DeckCard(card.suitIndex, check_rank)
                if check_card in stored_cards:
                    stacks[card.suitIndex] += 1
                    stored_cards.remove(check_card)
                    if check_card in stored_crits:
                        stored_crits.remove(check_card)
                else:
                    break
        elif card.rank <= stacks[card.suitIndex]:
            pass  # card is trash
        elif card.rank > stacks[card.suitIndex] + 1:
            # need to store card
            if card in stored_cards or card.rank == 5 or card in artificial_crits:
                stored_crits.add(card)
            stored_cards.add(card)

        hand_size_left_for_crits = instance.num_players * instance.hand_size - len(stored_crits) - 1

        # In case we can only keep the critical cards exactly, get rid of all others
        if hand_size_left_for_crits == 0 and do_squeeze:
            # Note the very important copy here (!)
            stored_cards = stored_crits.copy()
            squeeze = True

        # Use a bool flag to only mark this reason once
        if hand_size_left_for_crits < 0 and not hand_size_found:
            reasons.infeasibility_reasons.append(InfeasibilityReason(InfeasibilityType.HandSize, card_index))
            hand_size_found = True

        max_remaining_plays = (instance.deck_size - card_index - 1) + instance.num_players
        needed_plays = instance.max_score - sum(stacks)
        cur_pace = max_remaining_plays - needed_plays
        if cur_pace <= 0 and (list_all_pace_cuts or (not pace_found)):
            if squeeze:
                # We checked single-suit pace losses beforehand (which can only occur in 2p)
                # The value we store is the number of cards still left in the deck
                reasons.infeasibility_reasons.append(InfeasibilityReason(InfeasibilityType.PaceAfterSqueeze, instance.deck_size - card_index - 1))
            else:
                reasons.infeasibility_reasons.append(InfeasibilityReason(InfeasibilityType.Pace, instance.deck_size - card_index - 1))

            pace_found = True

#        if card_index != instance.deck_size - 1:
        reasons.min_pace.update(cur_pace, card_index)
        reasons.max_stored_cards.update(len(stored_cards), card_index)
        reasons.max_stored_crits.update(len(stored_crits), card_index)

    return reasons


def analyze(instance: hanab_game.HanabiInstance, list_all_pace_cuts: bool = False) -> AnalysisResult:
    # Check for pace and hand size problems:
    result = analyze_pace_and_hand_size(instance, do_squeeze=True, list_all_pace_cuts=list_all_pace_cuts)
    # In case pace ran out after a squeeze from hand size, we want to run a clean pace analysis again
    if any(map(lambda r: r.type == InfeasibilityType.PaceAfterSqueeze, result.infeasibility_reasons)):
        result.infeasibility_reasons += analyze_pace_and_hand_size(instance, False, list_all_pace_cuts).infeasibility_reasons

    # Top/bottom deck losses in a single suit.
    top_bottom_deck_loss = check_for_top_bottom_deck_loss(instance)
    if top_bottom_deck_loss is not None:
        result.infeasibility_reasons.append(InfeasibilityReason(InfeasibilityType.BottomTopDeck, top_bottom_deck_loss))

    # Special cases of pace loss, categorization for 2p only
    if instance.num_players == 2:
        result.infeasibility_reasons += analyze_2p_bottom_loss(instance)

    # check for critical non-fives at the bottom of the deck
    bottom_card = instance.deck[-1]
    if bottom_card.rank != 5 and bottom_card.suitIndex in instance.dark_suits:
        result.infeasibility_reasons.append(InfeasibilityReason(
            InfeasibilityType.CritAtBottom,
            instance.deck_size - 1
        ))

    # cleanup reasons to unique
    result.infeasibility_reasons = list(set(result.infeasibility_reasons))
    return result


def run_on_database(variant_id, list_all_pace_cuts: bool = False):
    database.cur.execute(
        "SELECT seed, num_players, deck FROM seeds WHERE variant_id = (%s) ORDER BY (num_players, seed)",
        (variant_id,)
    )
    res = database.cur.fetchall()
    logger.verbose("Checking {} seeds of variant {} for infeasibility".format(len(res), variant_id))
    with alive_progress.alive_bar(total=len(res), title='Check for infeasibility reasons in var {}'.format(variant_id)) as bar:
        for (seed, num_players, deck_str) in res:
            deck = compress.decompress_deck(deck_str)
            result = analyze(hanab_game.HanabiInstance(deck, num_players), list_all_pace_cuts=list_all_pace_cuts)
            for reason in result.infeasibility_reasons:
                database.cur.execute(
                    "INSERT INTO score_upper_bounds (seed, score_upper_bound, reason) "
                    "VALUES (%s,%s,%s) "
                    "ON CONFLICT (seed, reason) DO UPDATE "
                    "SET score_upper_bound = EXCLUDED.score_upper_bound",
                    (seed, reason.score_upper_bound, reason.type.value)
                )
                database.cur.execute(
                    "UPDATE seeds SET feasible = (%s) WHERE seed = (%s)",
                    (False, seed)
                )
            bar()
    database.conn.commit()


def main():
    seed = "p5v0sporcupines-underclass-phantasmagorical"
    seed = 'p5c1s98804'
    seed = 'p4c1s1116'
    seed = 'p5c1s14459'
    num_players = 5
    database.global_db_connection_manager.read_config()
    database.global_db_connection_manager.connect()

    database.cur.execute("SELECT seed, num_players FROM seeds WHERE (feasible IS NULL OR feasible = false) AND class = 1 AND num_players = 5")
#    for (seed, num_players) in database.cur.fetchall():
    for _ in range(1):
        deck = database.games_db_interface.load_deck(seed)
        inst = hanabi.hanab_game.HanabiInstance(deck, num_players)
        lost =  check_for_top_bottom_deck_loss(inst)
        if lost:
            print(seed)


if __name__ == "__main__":
    main()