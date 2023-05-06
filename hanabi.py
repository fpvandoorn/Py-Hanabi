from typing import Optional, List
from enum import Enum
from termcolor import colored

import constants


class DeckCard():
    def __init__(self, suitIndex: int, rank: int, deck_index=None):
        self.suitIndex: int = suitIndex
        self.rank: int = rank
        self.deck_index: Optional[int] = deck_index

    @staticmethod
    def from_json(deck_card):
        return DeckCard(**deck_card)

    def colorize(self):
        color = ["green", "blue", "magenta", "yellow", "white", "cyan"][self.suitIndex]
        return colored(str(self), color)

    def __eq__(self, other):
        return self.suitIndex == other.suitIndex and self.rank == other.rank

    def __repr__(self):
        return constants.COLOR_INITIALS[self.suitIndex] + str(self.rank)

    def __hash__(self):
        # should be injective enough, we never use cards with ranks differing by 1000
        return 1000 * self.suitIndex + self.rank

def pp_deck(deck: List[DeckCard]) -> str:
    return "[" + ", ".join(card.colorize() for card in deck) + "]"



class ActionType(Enum):
    Play = 0
    Discard = 1
    ColorClue = 2
    RankClue = 3
    EndGame = 4
    VoteTerminate = 5 ## hack: online, this is encoded as a 10


class Action():
    def __init__(self, type_: ActionType, target: int, value: Optional[int] = None):
        self.type = type_
        self.target = target
        self.value = value

    @staticmethod
    def from_json(action):
        return Action(
                ActionType(action['type']),
                int(action['target']),
                action.get('value', None)
                )

    def __repr__(self):
        match self.type:
            case ActionType.Play:
                return "Play card {}".format(self.target)
            case ActionType.Discard:
                return "Discard card {}".format(self.target)
            case ActionType.ColorClue:
                return "Clue color {} to player {}".format(self.value, self.target)
            case ActionType.RankClue:
                return "Clue rank {} to player {}".format(self.value, self.target)
            case ActionType.EndGame:
                return "Player {} ends the game (code {})".format(self.target, self.value)
            case ActionType.VoteTerminate:
                return "Players vote to terminate the game (code {})".format(self.value)
        return "Undefined action"


class HanabiInstance():
    def __init__(
            self,
            deck: List[DeckCard],               # assumes a default deck, every suit has to be distributed either [1,1,1,2,2,3,3,4,4,5] or [1,2,3,4,5]
            num_players: int,                   # number of players that play this deck, in range [2,6]
            hand_size: Optional[int]   = None,  # number of cards that each player holds
            num_strikes: Optional[int] = None,  # number of strikes that leads to game loss
            variant_id: Optional[int]  = None   # optional: variant id of hanab.live, useful if instance gets exported to be viewed in browser
        ):
        assert(2 <= num_players <= 6)
        
        # defining properties
        self.deck = deck
        self.num_players = num_players
        self.hand_size = hand_size or constants.HAND_SIZES[self.num_players]
        self.num_strikes = num_strikes or constants.NUM_STRIKES

        # normalize deck indices
        for (idx, card) in enumerate(self.deck):
            card.deck_index = idx

        # deducable properties, to be calculated once
        self.num_suits = max(map(lambda c: c.suitIndex, deck)) + 1
        self.num_dark_suits = (len(deck) - 10 * self.num_suits) // (-5)
        self.player_names = constants.PLAYER_NAMES[:self.num_players]
        self.deck_size = len(self.deck)

        ## maximum number of moves in any game that can achieve max score
        # each suit gives 15 moves, as we can play and discard 5 cards each and give 5 clues. dark suits only give 5 moves, since no discards are added
        # number of cards that remain in players hands after end of game. they cost 2 turns each, since we cannot discard them and also have one clue less
        # 8 clues at beginning, one further clue for each suit but one (the clue of the last 5 is never useful since it is gained in the extra-round)
        # subtract a further move for a second 5-clue that can't be used in 5 or 6-player games, since the extraround starts too soon
        self.max_winning_moves = 15 * self.num_suits - 10 * self.num_dark_suits    \
                               - 2 * self.num_players * (self.hand_size - 1) \
                               + 8 + (self.num_suits - 1)                    \
                               + (-1 if self.num_players >= 5 else 0)

        # TODO: set a meaningful default here for export?
        self._variant_id: Optional[int] = variant_id

    @property
    def num_dealt_cards(self):
        return self.num_players * self.hand_size

    @property
    def draw_pile_size(self):
        return self.deck_size - self.num_dealt_cards

    @property
    def variant_id(self):
        if self._variant_id is not None:
            return self._variant_id
        else:
            # ensure no key error can happen
            assert(self.is_standard())
            return constants.VARIANT_IDS_STANDARD_DISTRIBUTIONS[self.num_suits][self.num_dark_suits]

    # returns True if the instance has values matching hanabi-live rules
    # (i.e. standard + extra variants with 5 / 6 suits)
    def is_standard(self):
        return all([
            2 <= self.num_players <= 6,
            self.hand_size == constants.HAND_SIZES[self.num_players],
            self.num_strikes == constants.NUM_STRIKES,
            3 <= self.num_suits <= 6,
            0 <= self.num_dark_suits <= 2,
            4 <= self.num_suits - self.num_dark_suits or self.num_suits == 3
            # TODO: check that variant id matches deck distribution
            ]
       )



class GameState():
    def __init__(self, instance: HanabiInstance):
        # will not be modified
        self.instance = instance

        # dynamic game state
        self.progress = self.instance.num_players * self.instance.hand_size     # index of next card to be drawn
        self.hands = [self.instance.deck[self.instance.hand_size * p : self.instance.hand_size * (p+1)] for p in range(0, self.instance.num_players)]
        self.stacks = [0 for i in range(0, self.instance.num_suits)]
        self.strikes = 0
        self.clues = 8
        self.turn = 0
        self.pace = self.instance.deck_size - 5 * self.instance.num_suits  - self.instance.num_players * (self.instance.hand_size - 1)
        self.remaining_extra_turns = self.instance.num_players + 1
        self.trash = []

        # can be set to true if game is known to be in a lost state
        self.in_lost_state = False

        # will track replay as game progresses
        self.actions = []


    ## Methods to control game state change

    def make_action(self, Action):
        match Action.ActionType:
            case ActionType.clue:
                self.clue()
            case ActionType.Play:
                self.play(action.target)

    def play(self, card_idx):
        card = self.instance.deck[card_idx]
        if card.rank == self.stacks[card.suitIndex] + 1:
            self.stacks[card.suitIndex] += 1
            if card.rank == 5 and self.clues != 8:
                self.clues += 1
        else:
            self.strikes += 1
            assert (self.strikes < self.instance.num_strikes)
            self.trash.append(self.instance.deck[card_idx])
        self.actions.append(Action(ActionType.Play, target=card_idx))
        self.__replace(card_idx)
        self.__make_turn()

    def discard(self, card_idx):
        assert(self.clues < 8)
        self.actions.append(Action(ActionType.Discard, target=card_idx))
        self.clues += 1
        self.pace -= 1
        self.trash.append(self.instance.deck[card_idx])
        self.__replace(card_idx)
        self.__make_turn()

    def clue(self):
        assert(self.clues > 0)
        self.actions.append(
                Action(
                    ActionType.RankClue,
                    target=(self.turn +1) % self.instance.num_players,                    # clue next plyaer
                    value=self.hands[(self.turn +1) % self.instance.num_players][0].rank  # clue index 0
                )
        )
        self.clues -= 1
        self.__make_turn()
    


    # Forward some properties of the underlying instance
    @property
    def num_players(self):
        return self.instance.num_players

    @property
    def num_suits(self):
        return self.instance.num_suits

    @property
    def num_dark_suits(self):
        return self.instance.num_dark_suits

    @property
    def deck(self):
        return self.instance.deck

    @property
    def hand_size(self):
        return self.instance.hand_size

    @property
    def deck_size(self):
        return self.instance.deck_size


    # Properties of GameState
    
    def is_over(self):
        return all(s == 5 for s in self.stacks) or (self.remaining_extra_turns == 0) or (self.is_known_lost())

    def is_won(self):
        return self.score == 5 * instance.num_suits

    def is_known_lost(self):
        return self.in_lost_state

    @property
    def score(self):
        return sum(self.stacks)

    @property
    def cur_hand(self):
        return self.hands[self.turn]
    

    # Utilities

    def holding_players(self, card):
        for (player, hand) in enumerate(self.hands):
            if card in hand:
                yield player


    def to_json(self):
        # ensure we have at least one action
        if len(self.actions) == 0:
            self.actions.append(Action(
                ActionType.EndGame,
                target=0
                )
            )
        return {
            "deck": self.instance.deck,
            "players": self.instance.player_names,
            "actions": self.actions,
            "first_player": 0,
            "options": {
                "variant": "No Variant",
                }
            }
    
    # Private helpers
    
    # increments turn counter and tracks extra round
    def __make_turn(self):
        assert(self.remaining_extra_turns > 0)
        self.turn = (self.turn + 1) % self.instance.num_players
        if self.progress == self.instance.deck_size:
            self.remaining_extra_turns -= 1

    # replaces the specified card (has to be in current player's hand) with the next card of the deck (if nonempty)
    def __replace(self, card_idx):
        idx_in_hand = next((i for (i, card) in enumerate(self.cur_hand) if card.deck_index == card_idx), None)

        assert(idx_in_hand is not None)

        for i in range(idx_in_hand, self.instance.hand_size - 1):
            self.cur_hand[i] = self.cur_hand[i + 1]
        if self.progress < self.instance.deck_size:
            self.cur_hand[self.instance.hand_size - 1] = self.instance.deck[self.progress]
            self.progress += 1

