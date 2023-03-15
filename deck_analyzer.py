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


def analyze(deck: List[DeckCard], num_players):
    num_suits = max(map(lambda c: c.suitIndex, deck)) + 1
    hand_size = STANDARD_HAND_SIZE[num_players]

    # we will sweep through the deck and pretend that we instantly play all cards
    # as soon as we have them (and recurse this)
    # this allows us to detect standard pace issue arguments

    stacks = [0] * num_suits
    stored_cards = set()
    min_forced_pace = 100
    for (i, card) in enumerate(deck):
        if card.rank == stacks[card.suitIndex] + 1:
            # card is playable
            stacks[card.suitIndex] += 1
            # check for further playables that we stored
            for check_rank in range(card.rank + 1, 6):
                check_card = DeckCard(card.suitIndex, check_rank)
                if check_card in stored_cards:
                    stacks[card.suitIndex] += 1
                    stored_cards.remove(check_card)
                else:
                    break
        elif card.rank <= stacks[card.suitIndex]:
            pass # card is trash
        elif card.rank > stacks[card.suitIndex] + 1:
            # need to store card
            stored_cards.add(card)

        # the last - 1 is there because we have to discard 'next', causing a further draw
        max_remaining_plays = (len(deck) - i - 1) + num_players - 1

        needed_plays = 5 * num_suits - sum(stacks)
        missing =  max_remaining_plays - needed_plays
        min_forced_pace = min(min_forced_pace, missing)

    return min_forced_pace


def run_on_database():
    cur = conn.cursor()
    cur.execute("SELECT seed, num_players, deck from seeds where variant_id = 0 order by num_players desc")
    for (seed, num_players, deck) in cur:
        p = analyze(decompress_deck(deck), num_players)
        if p < 0:
            print("seed {} runs out of pace".format(seed))

if __name__ == "__main__":
    print(deck)
    a = analyze(deck, 2)
    print(a)
    run_on_database()
