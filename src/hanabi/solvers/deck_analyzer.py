from enum import Enum
from typing import List

import alive_progress

from hanabi import database
from hanabi import logger
from hanabi import hanab_game
from hanabi.live import compress


class InfeasibilityType(Enum):
    OutOfPace = 0  # idx denotes index of last card drawn before being forced to reduce pace, value denotes how bad pace is
    OutOfHandSize = 1  # idx denotes index of last card drawn before being forced to discard a crit
    CritAtBottom = 3


class InfeasibilityReason:
    def __init__(self, infeasibility_type: InfeasibilityType, score_upper_bound, value=None):
        self.type = infeasibility_type
        self.score_upper_bound = score_upper_bound
        self.value = value

    def __repr__(self):
        match self.type:
            case InfeasibilityType.OutOfPace:
                return "Upper bound {}, since deck runs out of pace after drawing card {}".format(self.score_upper_bound, self.value)
            case InfeasibilityType.OutOfHandSize:
                return "Upper bound {}, since deck runs out of hand size after drawing card {}".format(self.score_upper_bound, self.value)
            case InfeasibilityType.CritAtBottom:
                return "Upper bound {}, sicne deck has critical non-5 at bottom".format(self.score_upper_bound)


def analyze(instance: hanab_game.HanabiInstance, only_find_first=False) -> List[InfeasibilityReason]:
    """
    Checks instance for the following (easy) certificates for unfeasibility
    - There is a critical non-5 at the bottom
    - We necessarily run out of pace when playing this deck:
        At some point, among all drawn cards, there are too few playable ones so that the next discard
        reduces pace to a negative amount
    - We run out of hand size when playing this deck:
        At some point, there are too many critical cards (that also could not have been played) for the players
        to hold collectively
    :param instance: Instance to be analyzed
    :param only_find_first: If true, we immediately return when finding the first infeasibility reason and don't
        check for further ones. Might be slightly faster on some instances, especially dark ones.
    :return: List with all reasons found. Empty if none is found.
        In particular, if return value is not the empty list, the analyzed instance is unfeasible
    """
    reasons = []

    # check for critical non-fives at bottom of the deck
    bottom_card = instance.deck[-1]
    if bottom_card.rank != 5 and bottom_card.suitIndex in instance.dark_suits:
        reasons.append(InfeasibilityReason(
            InfeasibilityType.CritAtBottom,
            instance.max_score - 5 + bottom_card.rank,
            instance.deck_size - 1
        ))
        if only_find_first:
            return reasons

    # we will sweep through the deck and pretend that
    # - we keep all non-trash cards in our hands
    # - we instantly play all playable cards as soon as we have them
    # - we recurse on this instant-play
    #
    # For example, we assume that once we draw r2, we check if we can play r2.
    # If yes, then we also check if we drew r3 earlier and so on.
    # If not, then we keep r2 in our hands
    #
    # In total, this is equivalent to assuming that we infinitely many clues
    # and infinite storage space in our hands (which is of course not true),
    # but even in this setting, some games are infeasible due to pace issues
    # that we can detect
    #
    # A small refinement is to pretend that we only have infinite storage for non-crit cards,
    # for crit-cards, the usual hand card limit applies.
    # This allows us to detect some seeds where there are simply too many unplayable cards to hold at some point
    # that also can't be discarded
    # this allows us to detect standard pace issue arguments

    stacks = [0] * instance.num_suits

    # we will ensure that stored_crits is a subset of stored_cards
    stored_cards = set()
    stored_crits = set()

    min_forced_pace = instance.initial_pace
    worst_pace_index = 0

    max_forced_crit_discard = 0
    worst_crit_index = 0

    for (i, card) in enumerate(instance.deck):
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
            if card in stored_cards or card.rank == 5 or card == instance.deck[-1]:
                stored_crits.add(card)
            stored_cards.add(card)


        # check for out of handsize (this number can be negative, in which case nothing applies)
        # Note the +1 at the end, which is there because we have to discard next,
        # so even if we currently have as many crits as we can hold, we have to discard one
        num_forced_crit_discards = len(stored_crits) - instance.num_players * instance.hand_size + 1
        if num_forced_crit_discards > max_forced_crit_discard:
            worst_crit_index = i
            max_forced_crit_discard = num_forced_crit_discards
            if only_find_first:
                reasons.append(InfeasibilityReason(
                    InfeasibilityType.OutOfPace,
                    instance.max_score + min_forced_pace,
                    worst_pace_index
                ))
                return reasons

        # the last - 1 is there because we have to discard 'next', causing a further draw
        max_remaining_plays = (instance.deck_size - i - 1) + instance.num_players - 1
        needed_plays = instance.max_score - sum(stacks)
        cur_pace = max_remaining_plays - needed_plays
        if cur_pace < min(0, min_forced_pace):
            min_forced_pace = cur_pace
            worst_pace_index = i
            if only_find_first:
                reasons.append(InfeasibilityReason(
                    InfeasibilityType.OutOfPace,
                    instance.max_score + min_forced_pace,
                    worst_pace_index
                ))
                return reasons

    # check that we correctly walked through the deck
    assert (len(stored_cards) == 0)
    assert (len(stored_crits) == 0)
    assert (sum(stacks) == instance.max_score)

    if max_forced_crit_discard > 0:
        reasons.append(
            InfeasibilityReason(
                InfeasibilityType.OutOfHandSize,
                instance.max_score - max_forced_crit_discard,
                worst_crit_index
            )
        )

    if min_forced_pace < 0:
        reasons.append(InfeasibilityReason(
            InfeasibilityType.OutOfPace,
            instance.max_score + min_forced_pace,
            worst_pace_index
        ))

    return reasons


def run_on_database(variant_id):
    database.cur.execute(
        "SELECT seed, num_players, deck FROM seeds WHERE variant_id = (%s) ORDER BY (num_players, seed)",
        (variant_id,)
    )
    res = database.cur.fetchall()
    logger.verbose("Checking {} seeds of variant {} for infeasibility".format(len(res), variant_id))
    with alive_progress.alive_bar(total=len(res), title='Check for infeasibility reasons in var {}'.format(variant_id)) as bar:
        for (seed, num_players, deck_str) in res:
            deck = compress.decompress_deck(deck_str)
            reasons = analyze(hanab_game.HanabiInstance(deck, num_players))
            for reason in reasons:
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
