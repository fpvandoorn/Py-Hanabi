import collections
from compress import DeckCard, Action, ActionType, link, decompress_deck
from enum import Enum
from database import conn
from time import sleep


COLORS = 'rygbp'
STANDARD_HAND_SIZE = {2: 5, 3: 5, 4: 4, 5: 4, 6: 3}
NUM_STRIKES_TO_LOSE = 3

class CardType(Enum):
    Trash = 0
    Playable = 1
    Critical = 2
    Dispensable = 3


class CardState():
    def __init__(self, card_type: CardType, card: DeckCard, weight=1):
        self.card_type = card_type
        self.card = card
        self.weight = weight

    def __repr__(self):
        match self.card_type:
            case CardType.Trash:
                return "Trash ({})".format(self.card)
            case CardType.Playable:
                return "Playable ({}) with weight {}".format(self.card, self.weight)
            case CardType.Critical:
                return "Critical ({})".format(self.card)
            case CardType.Dispensable:
                return "Dispensable ({}) with weight {}".format(self.card, self.weight)


class GameState():
    def __init__(self, num_players, deck):
        assert ( 2 <= num_players <= 6)

        self.num_players = num_players
        self.deck = deck
        for (idx, card) in enumerate(self.deck):
            card.deck_index = idx
        self.deck_size = len(deck)
        self.num_suits = max(map(lambda c: c.suitIndex, deck)) + 1
        self.hand_size = STANDARD_HAND_SIZE[self.num_players]
        self.players = ["Alice", "Bob", "Cathy", "Donald", "Emily"][:self.num_players]
        
        # dynamic game state
        self.progress = self.num_players * self.hand_size     # index of next card to be drawn
        self.hands = [deck[self.hand_size * p : self.hand_size * (p+1)] for p in range(0, num_players)]
        self.stacks = [0 for i in range(0, self.num_suits)]
        self.strikes = 0
        self.clues = 8
        self.turn = 0
        self.pace = self.deck_size - 5 * self.num_suits  - self.num_players * (self.hand_size - 1)
        self.remaining_extra_turns = self.num_players + 1
        self.trash = []

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
            self.trash.append(self.deck[card_idx])
        self.actions.append(Action(ActionType.Play, target=card_idx))
        self.__replace(card_idx)
        self.__make_turn()

    def discard(self, card_idx):
        assert(self.clues < 8)
        self.actions.append(Action(ActionType.Discard, target=card_idx))
        self.clues += 1
        self.pace -= 1
        self.trash.append(self.deck[card_idx])
        self.__replace(card_idx)
        self.__make_turn()

    def clue(self):
        assert(self.clues > 0)
        self.actions.append(
                Action(
                    ActionType.RankClue,
                    target=(self.turn +1) % self.num_players,                    # clue next plyaer
                    value=self.hands[(self.turn +1) % self.num_players][0].rank  # clue index 0
                )
        )
        self.clues -= 1
        self.__make_turn()

    def to_json(self):
        return {
            "deck": self.deck,
            "players": self.players,
            "actions": self.actions,
            "first_player": 0,
            "options": {
                "variant": "No Variant",
                }
            }

    def card_type(self, card):
        played = self.stacks[card.suitIndex]
        if card.rank <= played:
            return CardType.Trash
        elif card.rank == played + 1:
            return CardType.Playable
        elif card.rank == 5 or card in self.trash:
            return CardType.Critical
        else:
            return CardType.Dispensable

    def is_over(self):
        return all(s == 5 for s in self.stacks) or self.remaining_extra_turns == 0

    def holding_players(self, card):
        for (player, hand) in enumerate(self.hands):
            if card in hand:
                yield player

    def score(self):
        return sum(self.stacks)

class GreedyStrategy():
    def __init__(self, game_state: GameState):
        self.game_state = game_state

        self.earliest_draw_times = []
        for s in range(0, game_state.num_suits):
            self.earliest_draw_times.append([])
            for r in range(1, 6):
                self.earliest_draw_times[s].append(max(
                        game_state.deck.index(DeckCard(s,r)) - game_state.hand_size * game_state.num_players + 1,
                        0 if r == 1 else self.earliest_draw_times[s][r - 2]
                ))

        # Currently, we do not add the time the 5 gets drawn to this, since this is rather a measurument on how
        # bad a suit is in terms of having to hold on to other cards that are not playable *yet*
        self.suit_badness = [sum(self.earliest_draw_times[s][:-1]) for s in range(0, game_state.num_suits)]

    def make_move(self):
        hand_states = [[CardState(self.game_state.card_type(card), card, None) for card in self.game_state.hands[p]] for p in range(self.game_state.num_players)]

        # find dupes in players hands, marke one card crit and the other one trash
        for states in hand_states:
            counter = collections.Counter(map(lambda state: state.card, states))
            for card in counter:
                if counter[card] >= 2:
                    state = next(cstate for cstate in states if cstate.card == card)
                    dupes_present = True
                    state.card_type = CardType.Trash

        for (player, states) in enumerate(hand_states):
            for state in states:
                if state.card_type == CardType.Playable:
                    copy_holders = list(self.game_state.holding_players(state.card))
                    copy_holders.remove(player)
                    connecting_holders = list(self.game_state.holding_players(DeckCard(state.card.suitIndex, state.card.rank + 1)))
                    if len(copy_holders) == 0:
                        state.weight = (3 if len(connecting_holders) > 0 else 1) * state.card.rank
                    else:
                        # TODO
                        state.weight = 0.5 * state.card.rank
                elif state.card_type == CardType.Dispensable:
                    try:
                        # TODO: consider duplicate in hand
                        copy_holders = list(self.game_state.holding_players(state.card))
                        copy_holders.remove(player)
                        nextCopy = self.game_state.deck[self.game_state.progress:].index(card)
                    except:
                        nextCopy = 1
#                    state.weight = self.suit_badness[state.card.suitIndex] * nextCopy + 2 * (5 - state.card.rank)
                    state.weight = nextCopy + 2 * (5 - state.card.rank)
        cur_hand = hand_states[self.game_state.turn]
        plays = [cstate for cstate in cur_hand if cstate.card_type == CardType.Playable]
        trash = next((cstate for cstate in cur_hand if cstate.card_type == CardType.Trash), None)

        if len(plays) > 0:
            play = max(plays, key=lambda s: s.weight)
            self.game_state.play(play.card.deck_index)
        elif self.game_state.clues == 8:
            self.game_state.clue()
        elif trash is not None:
            self.game_state.discard(trash.card.deck_index)
        elif self.game_state.clues == 0:
            dispensable = [cstate for cstate in cur_hand if cstate.card_type == CardType.Dispensable]
            if len(dispensable) == 0:
                raise ValueError("Lost critical card")
            else:
                discard = min(dispensable, key=lambda s: s.weight)
                self.game_state.discard(discard.card.deck_index)
        else:
            self.game_state.clue()

def test():
    # seed p4v0s148
    deck = decompress_deck("15wpspaodknlftabkpixbxiudqvrumhsgeakqucvgcrfmfhynwlj")
    gs = GameState(5, deck)
    print(gs.deck)

    strat = GreedyStrategy(gs)
    while not gs.is_over():
        strat.make_move()
#    print(strat.suit_badness)
#    print(COLORS)
#    strat.make_move()
    print(gs.actions)
    print(link(gs.to_json()))


wins = open("won_seeds.txt", "a")
losses = open("lost_seeds.txt", "a")

lost = 0
won = 0
crits_lost = 0

def run_deck(seed, num_players, deck_str):
    global lost
    global won
    global crits_lost
    deck = decompress_deck(deck_str)
    gs = GameState(num_players, deck)
    strat = GreedyStrategy(gs)
    try:
        while not gs.is_over():
            strat.make_move()
        if not gs.score() == 25:
            losses.write("Seed {:10} {}:\n{}\n".format(seed, str(deck), link(gs.to_json())))
            lost += 1
        else:
#            wins.write("Seed {:10} {}:\n{}\n".format(seed, str(deck), link(gs.to_json())))
            won += 1
    except ValueError:
#        losses.write("Seed {} {}lost crit:\n{}\n".format(seed, str(deck), link(gs.to_json())))
        crits_lost += 1

if __name__ == "__main__":
    cur = conn.cursor()
    cur.execute("SELECT seed, num_players, deck FROM seeds WHERE variant_id = 0 AND num_players = 2 limit 1000")
    print()
    for r in cur:
        run_deck(*r)
        print("won: {:4}, lost: {:4}, crits lost: {:3}".format(won, lost, crits_lost), end = "\r")
    print()
