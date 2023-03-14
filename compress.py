import json
from enum import Enum
from typing import List, Optional
import more_itertools
from variants import variant_id, variant_name


BASE62 = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ";
COLORS = 'rygbpt'


# Helper method, iterate over chunks of length n in a string
def chunks(s: str, n: int):
    for i in range(0, len(s), n):
        yield s[i:i+n]


class DeckCard():
    def __init__(self, suitIndex: int, rank: int, deck_index=None):
        self.suitIndex: int = suitIndex
        self.rank: int = rank
        self.deck_index = deck_index

    @staticmethod
    def from_json(deck_card):
        return DeckCard(**deck_card)

    def __eq__(self, other):
        return self.suitIndex == other.suitIndex and self.rank == other.rank

    def __repr__(self):
        return COLORS[self.suitIndex] + str(self.rank)

    def __hash__(self):
        # should be injective enough, we never use cards with ranks differing by 1000
        return 1000 * self.suitIndex + self.rank


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
            value = 0
            with open('vote_terminate_actions.txt', 'a') as f:
                f.write('target: {}, value: {}, game_id: {}\n'.format(action.target, action.value, game_id))
        a = BASE62[typeRange * value + (action.type.value - minType)]
        b = BASE62[action.target] 
        return a + b
    out = str(minType) + str(maxType)
    out += ''.join(map(compress_action, actions))
    return out


def decompress_actions(actions_str: str) -> List[Action]:
    try:
        minType = int(actions_str[0])
        maxType = int(actions_str[1])
    except ValueError:
        raise ValueError("invalid action string: invalid min/max range")
    assert(maxType >= minType)
    if not len(actions_str) % 2 == 0:
            raise ValueError("Invalid length of action str")
    typeRange = maxType - minType + 1
    def decompress_action(action):
        actionType = ActionType((BASE62.index(action[0]) % typeRange) + minType)
        value = None
        if actionType not in [actionType.Play, actionType.Discard]:
            ## We encode values with +1 to differentiate null (encoded 0) and 0 (encoded 1)
            value = BASE62.index(action[0]) // typeRange - 1
            if value == -1:
                value = None
        target = BASE62.index(action[1])
        return Action(actionType, target, value)
    return [decompress_action(a) for a in chunks(actions_str[2:], 2)]


def compress_deck(deck: List[DeckCard]) -> str:
    assert(len(deck) != 0)
    minRank = min(map(lambda c: c.rank, deck))
    maxRank = max(map(lambda c: c.rank, deck))
    rankRange = maxRank - minRank + 1
    def compress_card(card):
        return BASE62[rankRange * card.suitIndex + (card.rank - minRank)]
    out = str(minRank) + str(maxRank)
    out += ''.join(map(compress_card, deck))
    return out


def decompress_deck(deck_str: str) -> List[DeckCard]:
    assert(len(deck_str) >= 2)
    minRank = int(deck_str[0])
    maxRank = int(deck_str[1])
    assert(maxRank >= minRank)
    rankRange = maxRank - minRank + 1
    def decompress_card(card_char):
        index = BASE62.index(card_char)
        suitIndex = index // rankRange
        rank = index % rankRange + minRank
        return DeckCard(suitIndex, rank)
    return [decompress_card(c) for c in deck_str[2:]]


def compressJSONGame(game_json: dict) -> str:
    out = ""
    num_players = len(game_json.get('players', []))
    num_players = game_json.get('num_players', num_players)
    if not 2 <= num_players:
        raise ValueError("Invalid JSON game: could not parse num players")
    out = "{}".format(num_players)
    try:
        deck = game_json['deck']
    except:
        raise KeyError("JSON game contains no deck")
    assert(len(deck) > 0)
    if type(deck[0]) != DeckCard:
        try:
            deck = [DeckCard.from_json(card) for card in deck]
        except:
            raise ValueError("invalid jSON format: could not convert to deck cards")
    # now, deck is in the correct form
    out += compress_deck(deck)
    out += ","   # first part finished
    actions = game_json.get('actions', [])
    if len(actions) == 0:
        print("WARNING: action array is empty")
    else:
        if type(actions[0]) != Action:
            try:
                actions = [Action.from_json(action) for action in actions]
            except:
                raise ValueError("invalid JSON format: could not convert to actions")
    out += compress_actions(actions)
    out += ","
    variant = game_json.get("variant", "No Variant")
    out += str(variant_id(variant))
    return ''.join(more_itertools.intersperse("-", out, 20))


def decompressJSONGame(game_str: str)->dict:
    game = {}
    game_str = game_str.replace("-", "")
    try:
        [players_deck, actions, variant_id] = game_str.split(",")
    except:
        raise ValueError("Invalid format of compressed string!")
    game['players'] = ["Alice", "Bob", "Cathy", "Donald", "Emily"][:int(players_deck[0])]
    game['deck'] = decompress_deck(players_deck[1:])
    game['actions'] = decompress_actions(actions)
    game['options'] = {
            "variant": variant_name(int(variant_id))
            }
    return game

def link(game_json: dict) -> str:
    compressed = compressJSONGame(game_json)
    return "https://hanab.live/replay-json/{}".format(compressed)

