from typing import List, Union

import more_itertools

from hanabi import hanab_game
from hanabi.live import hanab_live

# use same BASE62 as on hanab.live to encode decks
BASE62 = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


# Helper method, iterate over chunks of length n in a string
def chunks(s: str, n: int):
    for i in range(0, len(s), n):
        yield s[i:i + n]


# exception thrown by decompression methods if parsing fails
class InvalidFormatError(ValueError):
    pass


def compress_actions(actions: List[hanab_game.Action]) -> str:
    min_type = 0
    max_type = 0
    if len(actions) != 0:
        min_type = min(map(lambda a: a.type.value, actions))
        max_type = max(map(lambda a: a.type.value, actions))
    type_range = max_type - min_type + 1

    def compress_action(action):
        # We encode action values with +1 to differentiate
        # null (encoded 0) and 0 (encoded 1)
        value = 0 if action.value is None else action.value + 1
        if action.type == hanab_game.ActionType.VoteTerminate:
            # This is currently a hack, the actual format has a 10 here,
            # but we cannot encode this
            value = 0
        try:
            a = BASE62[type_range * value + (action.type.value - min_type)]
            b = BASE62[action.target]
        except IndexError as e:
            raise ValueError("Encoding action failed, value too large, found {}".format(value)) from e
        return a + b

    return "{}{}{}".format(
        min_type,
        max_type,
        ''.join(map(compress_action, actions))
    )


def decompress_actions(actions_str: str) -> List[hanab_game.Action]:
    if not len(actions_str) >= 2:
        raise InvalidFormatError("min/max range not specified, found: {}".format(actions_str))
    try:
        min_type = int(actions_str[0])
        max_type = int(actions_str[1])
    except ValueError as e:
        raise InvalidFormatError(
            "min/max range of actions not specified, expected two integers, found {}".format(actions_str[:2])
        ) from e
    if not min_type <= max_type:
        raise InvalidFormatError("min/max range illegal, found [{},{}]".format(min_type, max_type))
    type_range = max_type - min_type + 1

    if not len(actions_str) % 2 == 0:
        raise InvalidFormatError("Invalid action string length: Expected even number of characters")

    for (index, char) in enumerate(actions_str[2:]):
        if char not in BASE62:
            raise InvalidFormatError(
                "Invalid character at index {}: Found {}, expected one of {}".format(
                    index, char, BASE62
                )
            )

    def decompress_action(action_idx: int, action: str):
        try:
            action_type_value = (BASE62.index(action[0]) % type_range) + min_type
            action_type = hanab_game.ActionType(action_type_value)
        except ValueError as e:
            raise InvalidFormatError(
                "Invalid action type at action {}: Found {}, expected one of {}".format(
                    action_idx, action_type_value,
                    [action_type.value for action_type in hanab_game.ActionType]
                )
            ) from e

        # We encode values with +1 to differentiate null (encoded 0) and 0 (encoded 1)
        value = BASE62.index(action[0]) // type_range - 1
        if value == -1:
            value = None
        if action_type in [hanab_game.ActionType.Play, hanab_game.ActionType.Discard]:
            if value is not None:
                raise InvalidFormatError(
                    "Invalid action value: Action at action index {} is Play/Discard, expected value None, "
                    "found: {}".format(action_idx, value)
                )
        target = BASE62.index(action[1])
        return hanab_game.Action(action_type, target, value)

    return [decompress_action(idx, a) for (idx, a) in enumerate(chunks(actions_str[2:], 2))]


def compress_deck(deck: List[hanab_game.DeckCard]) -> str:
    assert (len(deck) != 0)
    min_rank = min(map(lambda card: card.rank, deck))
    max_rank = max(map(lambda card: card.rank, deck))
    rank_range = max_rank - min_rank + 1

    def compress_card(card):
        try:
            return BASE62[rank_range * card.suitIndex + (card.rank - min_rank)]
        except IndexError as e:
            raise InvalidFormatError(
                "Could not compress card, suit or rank too large. Found: {}".format(card)
            ) from e

    return "{}{}{}".format(
        min_rank,
        max_rank,
        ''.join(map(compress_card, deck))
    )


def decompress_deck(deck_str: str) -> List[hanab_game.DeckCard]:
    if len(deck_str) < 2:
        raise InvalidFormatError("min/max rank range not specified, found: {}".format(deck_str))
    try:
        min_rank = int(deck_str[0])
        max_rank = int(deck_str[1])
    except ValueError as e:
        raise InvalidFormatError(
            "min/max rank range not specified, expected two integers, found {}".format(deck_str[:2])
        ) from e
    if not max_rank >= min_rank:
        raise InvalidFormatError(
            "Invalid rank range, found [{},{}]".format(min_rank, max_rank)
        )
    rank_range = max_rank - min_rank + 1

    for (index, char) in enumerate(deck_str[2:]):
        if char not in BASE62:
            raise InvalidFormatError(
                "Invalid character at index {}: Found {}, expected one of {}".format(
                    index, char, BASE62
                )
            )

    def decompress_card(card_char):
        encoded = BASE62.index(card_char)
        suit_index = encoded // rank_range
        rank = encoded % rank_range + min_rank
        return hanab_game.DeckCard(suit_index, rank)

    return [decompress_card(card) for card in deck_str[2:]]


# compresses a standard GameState object into hanab.live format
# which can be used in json replay links
# The GameState object has to be standard / fitting hanab.live variants,
# otherwise compression is not possible
def compress_game_state(state: Union[hanab_game.GameState, hanab_live.HanabLiveGameState]) -> str:
    if isinstance(state, hanab_live.HanabLiveGameState):
        var_id = state.instance.variant_id
    else:
        assert isinstance(state, hanab_game.GameState)
        var_id = hanab_live.HanabLiveInstance.select_standard_variant_id(state.instance)
    out = "{}{},{},{}".format(
        state.instance.num_players,
        compress_deck(state.instance.deck),
        compress_actions(state.actions),
        var_id
    )
    with_dashes = ''.join(more_itertools.intersperse("-", out, 20))
    return with_dashes


def decompress_game_state(game_str: str) -> hanab_live.HanabLiveGameState:
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

    instance = hanab_live.HanabLiveInstance(deck, num_players, variant_id)
    game = hanab_live.HanabLiveGameState(instance)

    # TODO: game is not in consistent state
    game.actions = actions
    return game


def link(game_state: hanab_game.GameState) -> str:
    compressed = compress_game_state(game_state)
    return "https://hanab.live/replay-json/{}".format(compressed)
