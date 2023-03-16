from compress import DeckCard
from typing import List
from enum import Enum
from compress import decompress_deck
import numpy
from database import conn

STANDARD_HAND_SIZE = {2: 5, 3: 5, 4: 4, 5: 4, 6: 3}
COLORS='rygbp'

deck_str = "15xaivliynfkrhpdwtprfaskwvfhnpcmjdksmlabcquqoegxugub"
deck = decompress_deck(deck_str)


class InfeasibilityType(Enum):
    OutOfPace = 0           # idx denotes index of last card drawn before being forced to reduce pace, value denotes how bad pace is
    OutOfHandSize = 1       # idx denotes index of last card drawn before being forced to discard a crit


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


def analyze(deck: List[DeckCard], num_players) -> InfeasibilityReason | None:
    num_suits = max(map(lambda c: c.suitIndex, deck)) + 1
    hand_size = STANDARD_HAND_SIZE[num_players]

    # we will sweep through the deck and pretend that we instantly play all cards
    # as soon as we have them (and recurse this)
    # this allows us to detect standard pace issue arguments

    stacks = [0] * num_suits
    stored_cards = set()
    stored_crits = set()
    min_forced_pace = 100
    worst_index = 0
    for (i, card) in enumerate(deck[:-2]):
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
        if len(stored_crits) == num_players * hand_size:
            return InfeasibilityReason(InfeasibilityType.OutOfHandSize, i)

        # the last - 1 is there because we have to discard 'next', causing a further draw
        max_remaining_plays = (len(deck) - i - 1) + num_players - 1

        needed_plays = 5 * num_suits - sum(stacks)
        missing =  max_remaining_plays - needed_plays
        if missing < min_forced_pace:
#            print("update to {}: {}".format(i, missing))
            min_forced_pace = missing
            worst_index = i
    if min_forced_pace < 0: 
        return InfeasibilityReason(InfeasibilityType.OutOfPace, worst_index, min_forced_pace)
    else:
        return None


def run_on_database():
    cur = conn.cursor()
    cur2 = conn.cursor()
    cur.execute("SELECT seed, num_players, deck from seeds where variant_id = 0 order by num_players desc")
    res = cur.fetchall()
    for (seed, num_players, deck) in res:
        deck = decompress_deck(deck)
        a = analyze(deck, num_players)
        if type(a) == InfeasibilityReason:
            if a.type == InfeasibilityType.OutOfHandSize:
                print("Seed {} infeasible: {}\n{}".format(seed, a, deck))
#        if p < 0:
#            print("seed {} ({} players) runs out of pace ({}) after drawing {}: {}:\n{}".format(seed, num_players, p, i, deck[i], deck))
#            cur.execute("UPDATE seeds SET feasible = f WHERE seed = (%s)", seed)

if __name__ == "__main__":
    print(deck)
    a = analyze(deck, 4)
    print(a)
    run_on_database()
