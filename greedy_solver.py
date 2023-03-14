# import numpy as np
from compress import DeckCard, Action, ActionType



COLORS = 'rygbp'
STANDARD_HAND_SIZE = {2: 5, 3: 5, 4: 4, 5: 4, 6: 3}
NUM_STRIKES_TO_LOSE = 3


class GameState():
    def __init__(self, num_players, deck):
        assert ( 2 <= num_players <= 6)

        self.num_players = num_players
        self.deck = deck
        self.deck_size = len(deck)
        self.num_suits = max(map(lambda c: c.suitIndex, deck)) + 1
        self.hand_size = STANDARD_HAND_SIZE[self.num_players]
        
        # dynamic game state
        self.progress = self.num_players * self.hand_size     # index of next card to be drawn
        self.hands = [deck[self.hand_size * p : self.hand_size * (p+1)] for p in range(0, num_players)]
        self.stacks = [0 for i in range(0, self.num_suits)]
        self.strikes = 0
        self.clues = 8
        self.turn = 0
        self.remaining_extra_turns = self.num_players + 1

        # will track replay as game progresses
        self.actions = []

    @property
    def cur_hand(self):
        return self.hands[self.turn]

    def __make_turn(self):
        assert(self.remaining_extra_turns > 0)
        self.turn = (self.turn + 1) % self.num_players
        if self.progress == self.deck_size:
            self.remaining_extra_turns -= 1

    def __replace(self, card_idx):
        idx_in_hand = self.cur_hand.index(self.deck[card_idx])
        for i in range(idx_in_hand, self.hand_size - 1):
            self.cur_hand[i] = self.cur_hand[i + 1]
        if self.progress < self.deck_size:
            self.cur_hand[self.hand_size - 1] = self.deck[self.progress]
            self.progress += 1

    def play(self, card_idx):
        card = self.deck[card_idx]
        if card.rank == self.stacks[card.suitIndex] + 1:
            self.stacks[card.suitIndex] += 1
            if card.rank == 5 and self.clues != 8:
                self.clues += 1
        else:
            self.strikes += 1
        self.actions.append(Action(ActionType.Play, target=card_idx))
        self.__replace(card_idx)
        self.__make_turn()

    def discard(self, card_idx):
        assert(self.clues < 8)
        self.actions.append(Action(ActionType.Discard, target=card_idx))
        self.clues += 1
        self.__replace(card_idx)
        self.__make_turn()

    def clue(self):
        assert(self.clues > 0)
        self.actions.append(
                Action(
                    ActionType.RankClue,
                    target=(self.turn +1) % self.num_players,               # clue next plyaer
                    value=self.hands[(self.turn +1) % self.num_players][0]  # clue index 0
                )
        )
        self.__make_turn()

def test():
    deck_str = 'p5 p3 b4 r5 y4 y4 y5 r4 b2 y2 y3 g5 g2 g3 g4 p4 r3 b2 b3 b3 p4 b1 p2 b1 b1 p2 p1 p1 g1 r4 g1 r1 r3 r1 g1 r1 p1 b4 p3 g2 g3 g4 b5 y1 y1 y1 r2 r2 y2 y3'
    deck = [DeckCard(COLORS.index(c[0]), int(c[1])) for c in deck_str.split(" ")]
    gs = GameState(5, deck)
    gs.play(2)
    gs.play(4)
    print(gs.hands, gs.actions)


if __name__ == "__main__":
    test()
