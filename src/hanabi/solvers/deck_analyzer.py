from enum import Enum
from typing import List
from dataclasses import dataclass

import alive_progress

from hanabi import database
from hanabi import logger
from hanabi import hanab_game
from hanabi.live import compress


class InfeasibilityType(Enum):
    Pace                   = 0  # idx denotes index of last card drawn before being forced to reduce pace, value denotes how bad pace is
    DoubleBottom2With5s    = 1  # same, special case for 2p
    TripleBottom1With5s    = 2  # same, special case for 2p
    MultiSuitBdr           = 3
    PaceAfterSqueeze       = 4
    HandSize               = 10  # idx denotes index of last card drawn before being forced to discard a crit
    HandSizeDirect         = 11
    HandSizeWithSqueeze    = 12
    HandSizeWithBdr        = 13
    HandSizeWithBdrSqueeze = 14

    # further reasons, currently not scanned for
    BottomTopDeck          = 20
    DoubleBottomTopDeck    = 30
    CritAtBottom           = 40
    SAT                    = 50


class InfeasibilityReason:
    def __init__(self, infeasibility_type: InfeasibilityType, value=None):
        self.type = infeasibility_type
        self.value = value


    def __repr__(self):
        return "{} ({})".format(self.type, self.value)
        match self.type:
            case InfeasibilityType.Pace:
                return "Out of Pace after drawing card {}".format(self.value)
            case InfeasibilityType.HandSize:
                return "Out of hand size after drawing card {}".format(self.value)
            case InfeasibilityType.CritAtBottom:
                return "Critical non-5 at bottom"



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
    considered_bdr = False
    artificial_crits = set()

    # Investigate BDRs. This catches special cases of Pace losses in 2p, as well as mark some cards critical because
    # their second copies cannot be used.
    filtered_deck = [card for card in instance.deck if card.rank != 5]
    if instance.num_players == 2:
        if filtered_deck[-1] == filtered_deck[-2] and filtered_deck[-1].rank == 2:
            reasons.append(InfeasibilityReason(InfeasibilityType.Pace, filtered_deck[-2].deck_index - 1))
            if only_find_first:
                return reasons
            reasons.append(InfeasibilityReason(InfeasibilityType.DoubleBottom2With5s, filtered_deck[-2].deck_index - 1))
            pace_found = True
        if filtered_deck[-1] == filtered_deck[-2] and filtered_deck[-2] == filtered_deck[-3] and filtered_deck[-3].rank == 1:
            reasons.append(InfeasibilityReason(InfeasibilityType.Pace, filtered_deck[-3].deck_index - 1))
            if only_find_first:
                return reasons
            reasons.append(InfeasibilityReason(InfeasibilityType.DoubleBottom2With5s, filtered_deck[-2].deck_index - 1))
            pace_found = True

        # In 2-player, the second-last card cannot be played if it is a 2
        if filtered_deck[-2].rank == 2:
            artificial_crits.add(filtered_deck[-2])

        # In 2-player, in case there is double bottom 3 of the same suit, the card immediately before cannot be played:
        # After playing that one and drawing the first 3, exactly 3,4,5 of the bottom suit have to be played
        if filtered_deck[-1] == filtered_deck[-2] and filtered_deck[-2].rank == 3:
            artificial_crits.add(filtered_deck[-2])

    # Last card in the deck can never be played
    artificial_crits.add(filtered_deck[-1])

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
            if card in stored_cards or card.rank == 5:
                stored_crits.add(card)
            elif card in artificial_crits:
                stored_crits.add(card)
                considered_bdr = True
            stored_cards.add(card)

        hand_size_left_for_crits = instance.num_players * instance.hand_size - len(stored_crits) - 1

        # In case we can only keep the critical cards exactly, get rid of all others
        if hand_size_left_for_crits == 0:
            # Note the very important copy here (!)
            stored_cards = stored_crits.copy()
            squeeze = True

        # Use a bool flag to only mark this reason once
        if hand_size_left_for_crits < 0 and not hand_size_found:
            reasons.append(InfeasibilityReason(
                InfeasibilityType.HandSize,
                i
            ))
            if only_find_first:
                return reasons
            hand_size_found = True

            # More detailed analysis of loss, categorization only
            if squeeze:
                if considered_bdr:
                    reasons.append(InfeasibilityReason(InfeasibilityType.HandSizeWithBdrSqueeze, i))
                else:
                    reasons.append(InfeasibilityReason(InfeasibilityType.HandSizeWithSqueeze, i))
            else:
                if considered_bdr:
                    reasons.append(InfeasibilityReason(InfeasibilityType.HandSizeWithBdr, i))
                else:
                    reasons.append(InfeasibilityReason(InfeasibilityType.HandSizeDirect, i))

        # the last - 1 is there because we have to discard 'next', causing a further draw
        max_remaining_plays = (instance.deck_size - i - 1) + instance.num_players - 1
        needed_plays = instance.max_score - sum(stacks)
        cur_pace = max_remaining_plays - needed_plays
        if cur_pace < 0 and not pace_found and not hand_size_found:
            reasons.append(InfeasibilityReason(
                InfeasibilityType.Pace,
                i
            ))
            if only_find_first:
                return reasons

            # We checked single-suit pace losses beforehand (which can only occur in 2p)
            if squeeze:
                reasons.append(InfeasibilityReason(InfeasibilityType.PaceAfterSqueeze, i))
            else:
                reasons.append(InfeasibilityReason(
                    InfeasibilityType.MultiSuitBdr,
                    i
                ))
            pace_found = True

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
