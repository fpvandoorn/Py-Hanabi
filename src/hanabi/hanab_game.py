from typing import Optional, List, Generator
from enum import Enum
from termcolor import colored

from hanabi import constants


class ParseError(ValueError):
    pass


class DeckCard:
    def __init__(self, suitIndex: int, rank: int, deck_index=None):
        self.suitIndex: int = suitIndex
        self.rank: int = rank
        self.deck_index: Optional[int] = deck_index

    @staticmethod
    def from_json(deck_card):
        suit_index = deck_card.get('suitIndex', None)
        rank = deck_card.get('rank', None)
        if suit_index is None:
            raise ParseError("No suit index specified in deck_card")
        if rank is None:
            raise ParseError("No rank specified in deck_card")
        return DeckCard(suit_index, rank)

    def to_json(self):
        return {
            "suitIndex": self.suitIndex,
            "rank": self.rank
        }

    def colorize(self):
        color = ["green", "blue", "magenta", "yellow", "white", "cyan"][self.suitIndex]
        return colored(str(self), color)

    def __eq__(self, other):
        return self.suitIndex == other.suitIndex and self.rank == other.rank

    def __repr__(self):
        if self.suitIndex == 0 and self.rank == 0:
            return "kt"
        return constants.COLOR_INITIALS[self.suitIndex] + str(self.rank)

    def __hash__(self):
        # should be injective enough, we never use cards with ranks differing by 1000
        return 1000 * self.suitIndex + self.rank


def pp_deck(deck: Generator[DeckCard, None, None]) -> str:
    return "[" + ", ".join(card.colorize() for card in deck) + "]"


class ActionType(Enum):
    Play = 0
    Discard = 1
    ColorClue = 2
    RankClue = 3
    EndGame = 4
    VoteTerminate = 5  ## hack: online, this is encoded as a 10


class Action:
    def __init__(self, type_: ActionType, target: int, value: Optional[int] = None):
        self.type = type_
        self.target = target
        self.value = value
        # enforce no values on play / discard
        if self.type in [ActionType.Discard, ActionType.Play]:
            self.value = None

    @staticmethod
    def from_json(action):
        action_type_int = action.get('type', None)
        action_target = action.get('target', None)
        action_value = action.get('value', None)
        if action_type_int is None:
            raise ParseError("No action type specified in action, found {}".format(action_type))
        if action_target is None:
            raise ParseError("No action target specified in action, found {}".format(action_target))
        for val in [action_type_int, action_target, action_value]:
            if val is not None and type(val) != int:
                raise ParseError("Invalid data type in action, expected int, found {}".format(type(val)))
        try:
            action_type = ActionType(action_type_int)
        except ValueError as e:
            raise ParseError("Invalid action type, found {}".format(action_type_int)) from e
        return Action(
            action_type,
            action_target,
            action_value
        )

    def to_json(self):
        return {
            "type": self.type.value,
            "target": self.target,
            "value": self.value
        }

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

    def __eq__(self, other):
        return self.type == other.type and self.target == other.target and self.value == other.value


class HanabiInstance:
    # TODO Max: Deal with the following variants:
    # - Critical fours (need to calculate dark suits differently)
    # - Reversed (need to store information somehow and pass this to the hanabi game class)
    # - Up or Down (in the long run we also want this, but seems a bit tedious, not needed now)
    def __init__(
            self,
            deck: List[DeckCard],
            # assumes a default deck, every suit has to be distributed either [1,1,1,2,2,3,3,4,4,5] or [1,2,3,4,5]
            num_players: int,  # number of players that play this deck, in range [2,6]

            hand_size: Optional[int] = None,  # number of cards that each player holds
            num_strikes: Optional[int] = None,  # number of strikes that leads to game loss
            clue_starved: bool = False,  # if true, discarding and playing fives only gives back half a clue
            fives_give_clue: bool = True,  # if false, then playing a five will not change the clue count
            deck_plays: bool = False,
            all_or_nothing: bool = False,
            starting_player: int = 0  # defines index of player that starts the game
    ):
        # defining properties
        self.deck = deck
        self.num_players = num_players
        self.hand_size = hand_size or constants.HAND_SIZES[self.num_players]
        self.num_strikes = num_strikes or constants.NUM_STRIKES
        self.clue_starved = clue_starved
        self.fives_give_clue = fives_give_clue
        self.deck_plays = deck_plays,
        self.all_or_nothing = all_or_nothing
        assert not self.all_or_nothing, "All or nothing not implemented"
        self.starting_player = starting_player

        # normalize deck indices
        for (idx, card) in enumerate(self.deck):
            card.deck_index = idx

        # deducable properties, to be calculated once
        self.num_suits = max(map(lambda c: c.suitIndex, deck)) + 1
        self.num_dark_suits = (len(deck) - 10 * self.num_suits) // (-5)
        self.player_names = constants.PLAYER_NAMES[:self.num_players]
        self.deck_size = len(self.deck)

        self.initial_pace = self.deck_size - 5 * self.num_suits - self.num_players * (self.hand_size - 1)

        # # maximum number of moves in any game that can achieve max score each suit gives 15 moves, as we can play
        # and discard 5 cards each and give 5 clues. dark suits only give 5 moves, since no discards are added number
        # of cards that remain in players hands after end of game. they cost 2 turns each, since we cannot discard
        # them and also have one clue less 8 clues at beginning, one further clue for each suit but one (the clue of
        # the last 5 is never useful since it is gained in the extra-round) subtract a further move for a second
        # 5-clue that can't be used in 5 or 6-player games, since the extraround starts too soon
        self.max_winning_moves = 15 * self.num_suits - 10 * self.num_dark_suits \
                                 - 2 * self.num_players * (self.hand_size - 1) \
                                 + 8 + (self.num_suits - 1) \
                                 + (-1 if self.num_players >= 5 else 0)

    @property
    def num_dealt_cards(self):
        return self.num_players * self.hand_size

    @property
    def draw_pile_size(self):
        return self.deck_size - self.num_dealt_cards

    @property
    def max_score(self):
        return 5 * self.num_suits

    @property
    def clue_increment(self):
        return 0.5 if self.clue_starved else 1

    @property
    def dark_suits(self):
        return list(range(self.num_suits - self.num_dark_suits, self.num_suits))


class GameState:
    def __init__(self, instance: HanabiInstance):
        # will not be modified
        self.instance = instance

        # dynamic game state
        self.progress = self.instance.num_players * self.instance.hand_size  # index of next card to be drawn
        self.hands = [self.instance.deck[self.instance.hand_size * p: self.instance.hand_size * (p + 1)] for p in
                      range(0, self.instance.num_players)]
        self.stacks = [0 for i in range(0, self.instance.num_suits)]
        self.strikes = 0
        self.clues = 8
        self.turn = self.instance.starting_player
        self.pace = self.instance.initial_pace
        self.remaining_extra_turns = self.instance.num_players + 1
        self.trash = []

        # can be set to true if game is known to be in a lost state
        self.in_lost_state = False

        # automatically set upon third strike, when extar round is over or when explicitly taking EndGame or
        # VoteTerminate actions
        self.over = False

        # will track replay as game progresses
        self.actions = []

    # Methods to control game state change

    def play(self, card_idx):
        card = self.instance.deck[card_idx]
        if card.rank == self.stacks[card.suitIndex] + 1:
            self.stacks[card.suitIndex] += 1
            if card.rank == 5 and self.clues != 8 and self.instance.fives_give_clue:
                self.clues += self.instance.clue_increment
        else:
            self.strikes += 1
            self.trash.append(self.instance.deck[card_idx])
            self.pace -= 1
        self.actions.append(Action(ActionType.Play, target=card_idx))
        self._replace(card_idx, allow_not_present=self.instance.deck_plays and (card_idx == self.deck_size - 1))
        self._make_turn()
        if all(s == 5 for s in self.stacks) or self.strikes >= self.instance.num_strikes:
            self.over = True

    def discard(self, card_idx):
        assert (self.clues < 8)
        self.actions.append(Action(ActionType.Discard, target=card_idx))
        self.clues += self.instance.clue_increment
        self.pace -= 1
        self.trash.append(self.instance.deck[card_idx])
        self._replace(card_idx)
        self._make_turn()

    def clue(self):
        assert (self.clues > 0)
        self.actions.append(self._waste_clue())
        self.clues -= 1
        self._make_turn()

    def make_action(self, action):
        match action.type:
            case ActionType.ColorClue | ActionType.RankClue:
                assert self.clues >= 1
                self.actions.append(action)
                self.clues -= 1
                self._make_turn()
                # TODO: could check that the clue specified is in fact legal
            case ActionType.Play:
                self.play(action.target)
            case ActionType.Discard:
                self.discard(action.target)
            case ActionType.EndGame | ActionType.VoteTerminate:
                self.actions.append(action)
                self.over = True

    def terminate(self):
        action = Action(ActionType.EndGame, 0, 0)
        self.make_action(action)

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

    @property
    def draw_pile_size(self):
        return self.deck_size - self.progress

    # Properties of GameState

    def is_over(self):
        return self.over or self.is_known_lost()

    def is_won(self):
        return self.score == self.instance.max_score

    def is_known_lost(self):
        return self.in_lost_state

    @property
    def score(self):
        if self.strikes >= self.instance.num_strikes:
            return 0
        return sum(self.stacks)

    @property
    def cur_hand(self):
        return self.hands[self.turn]

    # Utilities

    def is_playable(self, card: DeckCard):
        return self.stacks[card.suitIndex] + 1 == card.rank

    def is_trash(self, card: DeckCard):
        return self.stacks[card.suitIndex] >= card.rank

    def is_critical(self, card: DeckCard):
        if card.rank == 5:
            return True
        if self.is_trash(card):
            return False
        count = 0
        for hand in self.hands:
            count += hand.count(card)
        count += self.deck[self.progress:].count(card)
        return count == 1

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
            "deck": [card.to_json() for card in self.instance.deck],
            "players": self.instance.player_names,
            "actions": [action.to_json() for action in self.actions],
            "first_player": 0,
            "options": {
                "variant": "No Variant",
            }
        }

    # Query helpers for implementing bots
    def copy_holders(self, card: DeckCard, exclude_player: Optional[int]):
        return [
            player for player in range(self.num_players)
            if player != exclude_player and card in self.hands[player]
        ]

    @staticmethod
    def in_strict_order(player_a, player_b, player_c):
        """
        Check whether the three given players sit in order, where equality is not allowed
        :param player_a:
        :param player_b:
        :param player_c:
        :return:
        """
        return player_a < player_b < player_c or player_b < player_c < player_a or player_c < player_a < player_b

    def is_in_extra_round(self):
        return self.remaining_extra_turns <= self.instance.num_players

    # Private helpers

    # increments turn counter and tracks extra round
    def _make_turn(self):
        assert (not self.over)
        self.turn = (self.turn + 1) % self.instance.num_players
        if self.progress == self.instance.deck_size:
            self.remaining_extra_turns -= 1
            if self.remaining_extra_turns == 0:
                self.over = True

    # replaces the specified card (has to be in current player's hand) with the next card of the deck (if nonempty)
    def _replace(self, card_idx, allow_not_present: bool = False):
        try:
            idx_in_hand = next((i for (i, card) in enumerate(self.cur_hand) if card.deck_index == card_idx))
        except StopIteration:
            if not allow_not_present:
                raise
            self.progress += 1
            return

        for i in range(idx_in_hand, self.instance.hand_size - 1):
            self.cur_hand[i] = self.cur_hand[i + 1]
        if self.progress < self.instance.deck_size:
            self.cur_hand[self.instance.hand_size - 1] = self.instance.deck[self.progress]
            self.progress += 1

    # in HanabLiveInstances, this will be overridden with something that checks defaults
    def _waste_clue(self) -> Action:
        return Action(
            ActionType.RankClue,
            target=(self.turn + 1) % self.instance.num_players,  # clue next plyaer
            value=self.hands[(self.turn + 1) % self.instance.num_players][0].rank  # clue index 0
        )
