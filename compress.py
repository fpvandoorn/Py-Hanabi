import json
from enum import Enum
from typing import List, Optional

BASE62 = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ";

COLORS = 'rygbp'


## Helper method, iterate over chunks of length n in a string
def chunks(s: str, n: int):
    for i in range(0, len(s), n):
        yield s[i:i+n]


class DeckCard():
    def __init__(self, suitIndex: int, rank: int):
        self.suitIndex: int = suitIndex
        self.rank: int = rank

    def __eq__(self, other):
        return self.suitIndex == other.suitIndex and self.rank == other.rank

    def __repr__(self):
        return COLORS[self.suitIndex] + str(self.rank)


class ActionType(Enum):
    Play = 0
    Discard = 1
    ColorClue = 2
    RankClue = 3
    EndGame = 4

class Action():
    def __init__(self, type_: ActionType, target: int, value: Optional[int] = None):
        self.type = type_
        self.target = target
        self.value = value

    def __repr__(self):
        match self.type:
            case ActionType.Play:
                return "Play card {}".format(self.target)
            case ActionType.Discard:
                return "Discard card {}".format(self.target)
            case ActionType.ColorClue:
                return "Clue color {} to player {}".format(self.value, self.target)
            case ActionType.ColorClue:
                return "Clue rank {} to player {}".format(self.value, self.target)
            case ActionType.EndGame:
                return "Player {} ends the game (code {})".format(self.target, self.value)

def compress_actions(actions: List[Action]) -> str:
    minType = 0
    maxType = 0
    if len(actions) != 0:
        minType = min(map(lambda a: a.type.value, actions))
        maxType = max(map(lambda a: a.type.value, actions))
    typeRange = maxType - minType + 1
    def compress_action(action):
        value = 0 if action.value is None else action.value
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
        raise ValueError("invalid action string")
    assert(maxType >= minType)
    typeRange = maxType - minType + 1
    def decompress_action(action):
        actionType = ActionType(BASE62.index(action[0]) % typeRange)
        value = None
        if actionType not in [actionType.Play, actionType.Discard]:
            value = BASE62.index(action[0]) // typeRange
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



## test

deck = [DeckCard(0,1), DeckCard(2,4), DeckCard(4,5)]
c = compress_deck(deck)
l = decompress_deck(c)
print(deck, l)

f = [Action(ActionType.Discard, 2), Action(ActionType.Play, 3, 8)]
a = compress_actions(f)
x = decompress_actions(a)
print(a)
print(x)

c = '15ywseiijdqgholmnxcqrrxpvppvuukdkacakauswlmntfffbbgh'
l = decompress_deck(c)
print(l)
