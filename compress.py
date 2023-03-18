#! /bin/python3
import json
import sys
import more_itertools

from enum import Enum
from termcolor import colored
from typing import List, Optional

from variants import variant_id, variant_name
from hanabi import DeckCard, ActionType, Action, GameState, HanabiInstance


# use same BASE62 as on hanab.live to encode decks
BASE62 = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ";


# Helper method, iterate over chunks of length n in a string
def chunks(s: str, n: int):
    for i in range(0, len(s), n):
        yield s[i:i+n]


# exception thrown by decompression methods if parsing fails
class InvalidFormatError(ValueError):
        pass


def compress_actions(actions: List[Action], game_id=None) -> str:
    minType = 0
    maxType = 0
    if len(actions) != 0:
        minType = min(map(lambda a: a.type.value, actions))
        maxType = max(map(lambda a: a.type.value, actions))
    typeRange = maxType - minType + 1

    def compress_action(action):
        ## We encode action values with +1 to differentiate 
        # null (encoded 0) and 0 (encoded 1)
        value = 0 if action.value is None else action.value + 1
        if action.type == ActionType.VoteTerminate:
            # This is currently a hack, the actual format has a 10 here
            # but we cannot encode this
            value = 0
        try:
            a = BASE62[typeRange * value + (action.type.value - minType)]
            b = BASE62[action.target]
        except IndexError as e:
            raise ValueError("Encoding action failed, value too large, found {}".format(value)) from e
        return a + b

    return "{}{}{}".format(
            minType,
            maxType,
            ''.join(map(compress_action, actions))
    )


def decompress_actions(actions_str: str) -> List[Action]:
    if not len(actions_str) >= 2:
        raise InvalidFormatError("min/max range not specified, found: {}".format(actions_str))
    try:
        minType = int(actions_str[0])
        maxType = int(actions_str[1])
    except ValueError as e:
        raise InvalidFormatError(
                "min/max range of actions not specified, expected two integers, found {}".format(actions_str[:2])
        ) from e
    if not minType <= maxType:
        raise InvalidFormatError("min/max range illegal, found [{},{}]".format(minType, maxType))
    typeRange = maxType - minType + 1

    if not len(actions_str) % 2 == 0:
        raise InvalidFormatError("Invalid action string length: Expected even number of characters")

    for (index, char) in enumerate(actions_str[2:]):
        if not char in BASE62:
            raise InvalidFormatError(
                    "Invalid character at index {}: Found {}, expected one of {}".format(
                        index, char, BASE62
                        )
            )

    def decompress_action(index, action):
        try:
            action_type_value = (BASE62.index(action[0]) % typeRange) + minType
            action_type = ActionType(action_type_value)
        except ValueError as e:
            raise InvalidFormatError(
                    "Invalid action type at action {}: Found {}, expected one of {}".format(
                        index, actionTypeValue,
                        [action_type.value for action_type in ActionType]
                        )
            ) from e
        ## We encode values with +1 to differentiate null (encoded 0) and 0 (encoded 1)
        value = BASE62.index(action[0]) // typeRange - 1
        if value == -1:
            value = None
        if action_type in [ActionType.Play, ActionType.Discard]:
            if value is not None:
                raise InvalidFormatError(
                        "Invalid action value: Action at action index {} is Play/Discard, expected value None, found: {}".format(index, value)
                )
        target = BASE62.index(action[1])
        return Action(action_type, target, value)

    return [decompress_action(idx, a) for (idx, a) in enumerate(chunks(actions_str[2:], 2))]


def compress_deck(deck: List[DeckCard]) -> str:
    assert(len(deck) != 0)
    minRank = min(map(lambda c: c.rank, deck))
    maxRank = max(map(lambda c: c.rank, deck))
    rankRange = maxRank - minRank + 1

    def compress_card(card):
        try:
            return BASE62[rankRange * card.suitIndex + (card.rank - minRank)]
        except IndexError as e:
            raise InvalidFormatError(
                    "Could not compress card, suit or rank too large. Found: {}".format(card)
            ) from e
    return "{}{}{}".format(
            minRank,
            maxRank,
            ''.join(map(compress_card, deck))
    )


def decompress_deck(deck_str: str) -> List[DeckCard]:
    if len(deck_str) < 2:
        raise InvalidFormatError("min/max rank range not specified, found: {}".format(deck_str))
    try:
        minRank = int(deck_str[0])
        maxRank = int(deck_str[1])
    except ValueError as e:
        raise InvalidFormatError(
                "min/max rank range not specified, expected two integers, found {}".format(deck_str[:2])
        ) from e
    if not maxRank >= minRank:
        raise InvalidFormatError(
                "Invalid rank range, found [{},{}]".format(minRank, maxRank)
        )
    rankRange = maxRank - minRank + 1

    for (index, char) in enumerate(deck_str[2:]):
        if not char in BASE62:
            raise InvalidFormatError(
                    "Invalid character at index {}: Found {}, expected one of {}".format(
                        index, char, BASE62
                        )
            )

    def decompress_card(card_char):
        index = BASE62.index(card_char)
        suitIndex = index // rankRange
        rank = index % rankRange + minRank
        return DeckCard(suitIndex, rank)

    return [decompress_card(c) for c in deck_str[2:]]


# compresses a standard GameState object into hanab.live format
# which can be used in json replay links
# The GameState object has to be standard / fitting hanab.live variants,
# otherwise compression is not possible
def compress_game_state(state: GameState) -> str:
    if not state.instance.is_standard():
        raise ValueError("Cannot compress non-standard hanabi instance")
    out = "{}{},{},{}".format(
            state.instance.num_players,
            compress_deck(state.instance.deck),
            compress_actions(state.actions),
            state.instance.variant_id             # Note that a sane default is chosen if construction did not provide one
            )
    with_dashes = ''.join(more_itertools.intersperse("-", out, 20))
    return with_dashes


def decompress_game_state(game_str: str) -> GameState:
    game_str = game_str.replace("-", "")
    parts = game_str.split(",")
    if not len(parts) == 3:
        raise InvalidFormatError(
                "Expected 3 comma-separated parts of game, found {}".format(
                    len(parts)
                )
        )
    [players_deck, actions, variant_id] = parts
    if len(players_deck) == 0:
        raise InvalidFormatError("Expected nonempty first part")
    try:
        num_players = int(players_deck[0])
    except ValueError as e:
        raise InvalidFormatError(
            "Expected number of players, found: {}".format(players_deck[0])
        ) from e

    try:
        deck = decompress_deck(players_deck[1:])
    except InvalidFormatError as e:
        raise InvalidFormatError("Error while parsing deck") from e

    try:
        actions = decompress_actions(actions)
    except InvalidFormatError as e:
        raise InvalidFormatError("Error while parsing actions") from e

    try:
        variant_id = int(variant_id)
    except ValueError:
        raise ValueError("Expected variant id, found: {}".format(variant_id))

    instance = HanabiInstance(deck, num_players, variant_id=variant_id)
    game = GameState(instance)
    
    # TODO: game is not in consistent state
    game.actions = actions
    return game


def link(game_state: GameState) -> str:
    compressed = compress_game_state(game_state)
    return "https://hanab.live/replay-json/{}".format(compressed)


# add link method to GameState class
GameState.link = link



if __name__ == "__main__":
    for arg in sys.argv[1:]:
        deck = decompress_deck(arg)
        c = compress_deck(deck)
        assert(c == arg)
        print(deck)
        
        inst = HanabiInstance(deck, 5, variant_id = 32)
        game = GameState(inst)
        game.play(1)
        game.play(5)
        game.clue()
        print(game.link())

