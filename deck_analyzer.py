from compress import DeckCard
from typing import List
from enum import Enum

from database import conn
from hanabi import HanabiInstance
from compress import decompress_deck


class InfeasibilityType(Enum):
    OutOfPace = 0           # idx denotes index of last card drawn before being forced to reduce pace, value denotes how bad pace is
    OutOfHandSize = 1       # idx denotes index of last card drawn before being forced to discard a crit
    NotTrivial = 2


class InfeasibilityReason():
    def __init__(self, infeasibility_type, idx, value=None):
        self.type = infeasibility_type
        self.index = idx
        self.value = value

    def __repr__(self):
        match self.type:
            case InfeasibilityType.OutOfPace:
                return "Deck runs out of pace ({}) after drawing card {}".format(self.value, self.index)
            case InfeasibilityType.OutOfHandSize:
                return "Deck runs out of hand size after drawing card {}".format(self.index)


def analyze(instance: HanabiInstance, find_non_trivial=False) -> InfeasibilityReason | None:

    # we will sweep through the deck and pretend that we instantly play all cards
    # as soon as we have them (and recurse this)
    # this allows us to detect standard pace issue arguments

    stacks = [0] * instance.num_suits
    stored_cards = set()
    stored_crits = set()

    min_forced_pace = 100
    worst_index = 0

    ret = None

    for (i, card) in enumerate(instance.deck):
        if card.rank == stacks[card.suitIndex] + 1:
            # card is playable
            stacks[card.suitIndex] += 1
            # check for further playables that we stored
            for check_rank in range(card.rank + 1, 6):
                check_card = DeckCard(card.suitIndex, check_rank)
                if check_card in stored_cards:
                    stacks[card.suitIndex] += 1
                    stored_cards.remove(check_card)
                    if check_card in stored_crits:
                        stored_crits.remove(check_card)
                else:
                    break
        elif card.rank <= stacks[card.suitIndex]:
            pass # card is trash
        elif card.rank > stacks[card.suitIndex] + 1:
            # need to store card
            if card in stored_cards or card.rank == 5:
                stored_crits.add(card)
            stored_cards.add(card)
        
        ## check for out of handsize:
        if len(stored_crits) == instance.num_players * instance.hand_size:
            return InfeasibilityReason(InfeasibilityType.OutOfHandSize, i)

        if find_non_trivial and len(stored_cards) == instance.num_players * instance.hand_size:
            ret =  InfeasibilityReason(InfeasibilityType.NotTrivial, i)

        # the last - 1 is there because we have to discard 'next', causing a further draw
        max_remaining_plays = (instance.deck_size - i - 1) + instance.num_players - 1

        needed_plays = 5 * instance.num_suits - sum(stacks)
        missing =  max_remaining_plays - needed_plays
        if missing < min_forced_pace:
#            print("update to {}: {}".format(i, missing))
            min_forced_pace = missing
            worst_index = i

    # check that we correctly walked through the deck
    assert(len(stored_cards) == 0)
    assert(len(stored_crits) == 0)
    assert(sum(stacks) == 5 * instance.num_suits)

    if min_forced_pace < 0: 
        return InfeasibilityReason(InfeasibilityType.OutOfPace, worst_index, min_forced_pace)
    elif ret is not None:
        return ret
    else:
        return None


def run_on_database():
    cur = conn.cursor()
    cur2 = conn.cursor()
    for num_p in range(2, 6):
        cur.execute("SELECT seed, num_players, deck from seeds where variant_id = 0 and num_players = (%s) order by seed asc", (num_p,))
        res = cur.fetchall()
        hand = 0
        pace = 0
        non_trivial = 0
        d = None
        print("Checking {} {}-player seeds from database".format(len(res), num_p))
        for (seed, num_players, deck) in res:
            deck = decompress_deck(deck)
            a = analyze(HanabiInstance(deck, num_players), True)
            if type(a) == InfeasibilityReason:
                if a.type == InfeasibilityType.OutOfHandSize:
    #                print("Seed {} infeasible: {}\n{}".format(seed, a, deck))
                    hand += 1
                elif a.type == InfeasibilityType.OutOfPace:
                    pace += 1
                elif a.type == InfeasibilityType.NotTrivial:
                    non_trivial += 1
                    d = seed, deck

        print("Found {} seeds running out of hand size, {} running out of pace and {} that are not trivial".format(hand, pace, non_trivial))
        if d is not None:
            print("example non-trivial deck (seed {}): [{}]"
                  .format(
                      d[0],
                      ", ".join(c.colorize() for c in d[1])
                      )
                  )
        print()
#        if p < 0:
#            print("seed {} ({} players) runs out of pace ({}) after drawing {}: {}:\n{}".format(seed, num_players, p, i, deck[i], deck))
#            cur.execute("UPDATE seeds SET feasible = f WHERE seed = (%s)", seed)

if __name__ == "__main__":
#    print(deck)
#    a = analyze(deck, 4)
#    print(a)
    run_on_database()
