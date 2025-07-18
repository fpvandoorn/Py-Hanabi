from typing import List, Dict, Tuple

from hanabi.hanab_game import Action, ParseError
from hanabi import hanab_game
from hanabi import constants
from hanabi.live import variants


class HanabLiveInstance(hanab_game.HanabiInstance):
    def __init__(
            self,
            deck: List[hanab_game.DeckCard],
            num_players: int,
            variant_id: int,
            one_extra_card: bool = False,
            one_less_card: bool = False,
            *args, **kwargs
    ):
        self.one_extra_card = one_extra_card
        self.one_less_card = one_less_card
        assert 2 <= num_players <= 6
        hand_size = constants.HAND_SIZES[num_players]
        if one_less_card:
            hand_size -= 1
        if one_extra_card:
            hand_size += 1

        super().__init__(deck, num_players, hand_size=hand_size, *args, **kwargs)
        self.variant_id = variant_id
        self.variant = variants.Variant.from_db(self.variant_id)

    def __eq__(self, other):
        if not isinstance(other, HanabLiveInstance):
            return False
        return self.variant_id == other.variant_id and self.one_less_card == other.one_less_card and self.one_extra_card == other.one_extra_card and super().__eq__(other)


    @staticmethod
    def select_standard_variant_id(instance: hanab_game.HanabiInstance):
        err_msg = "Hanabi instance not supported by hanab.live, cannot convert to HanabLiveInstance: "
        assert 3 <= instance.num_suits <= 6, \
            err_msg + "Illegal number of suits ({}) found, must be in range [3,6]".format(instance.num_suits)
        assert 0 <= instance.num_dark_suits <= 2, \
            err_msg + "Illegal number of dark suits ({}) found, must be in range [0,2]".format(instance.num_dark_suits)
        assert 4 <= max(instance.num_suits, 4) - instance.num_dark_suits, \
            err_msg + "Illegal ratio of dark suits to suits, can have at most {} dark suits with {} total suits".format(
                max(instance.num_suits - 4, 0), instance.num_suits
            )
        return constants.VARIANT_IDS_STANDARD_DISTRIBUTIONS[instance.num_suits][instance.num_dark_suits]


def parse_json_game(game_json: Dict, as_hanab_live_instance: bool = True) \
        -> Tuple[HanabLiveInstance | hanab_game.HanabiInstance, List[Action]]:
    game_id = game_json.get('id', None)
    players = game_json.get('players', [])
    num_players = len(players)
    if num_players < 2 or num_players > 6:
        raise ParseError(num_players)

    options = game_json.get('options', {})
    var_name = options.get('variant', 'No Variant')
    deck_plays = options.get('deckPlays', False)
    one_extra_card = options.get('oneExtraCard', False)
    one_less_card = options.get('oneLessCard', False)
    all_or_nothing = options.get('allOrNothing', False)
    starting_player = options.get('startingPlayer', 0)
    detrimental_characters = options.get('detrimentalCharacters', False)

    try:
        actions = [hanab_game.Action.from_json(action) for action in game_json.get('actions', [])]
    except hanab_game.ParseError as e:
        raise ParseError("Failed to parse actions") from e

    try:
        deck = [hanab_game.DeckCard.from_json(card) for card in game_json.get('deck', None)]
    except hanab_game.ParseError as e:
        raise ParseError("Failed to parse deck") from e

    if detrimental_characters:
        raise NotImplementedError(
            "detrimental characters not supported, cannot determine score of game {}".format(game_id)
        )
    if as_hanab_live_instance:
        var_id = variants.variant_id(var_name)
        return HanabLiveInstance(
            deck, num_players, var_id,
            deck_plays=deck_plays,
            one_less_card=one_less_card,
            one_extra_card=one_extra_card,
            all_or_nothing=all_or_nothing,
            starting_player=starting_player
        ), actions
    else:
        hand_size = constants.HAND_SIZES[num_players]
        if one_less_card:
            hand_size -= 1
        if one_extra_card:
            hand_size += 1

        clue_starved = 'Clue Starved' in var_name

        return hanab_game.HanabiInstance(
            deck, num_players, hand_size,
            clue_starved=clue_starved,
            deck_plays=deck_plays,
            all_or_nothing=all_or_nothing,
            starting_player=starting_player
        ), actions



class HanabLiveGameState(hanab_game.GameState):
    def __init__(self, instance: HanabLiveInstance):
        super().__init__(instance)
        self.instance: HanabLiveInstance = instance

    def to_json(self):
        return {
            "actions": [action.to_json() for action in self.actions],
            "deck": [card.to_json() for card in self.deck],
            "players": ["Alice", "Bob", "Cathy", "Donald", "Emily", "Frank"][:self.num_players],
            "notes": [[]] * self.num_players,
            "options": {
                "variant": self.instance.variant_id,
                "deckPlays": self.instance.deck_plays,
                "oneExtraCard": self.instance.one_extra_card,
                "oneLessCard": self.instance.one_less_card,
                "allOrNothing": self.instance.all_or_nothing,
                "startingPlayer": self.instance.starting_player
            }
        }

    def _waste_clue(self) -> hanab_game.Action:
        for player in range(self.turn + 1, self.turn + self.num_players):
            for card in self.hands[player % self.num_players]:
                for rank in self.instance.variant.ranks:
                    if self.instance.variant.rank_touches(card, rank):
                        return hanab_game.Action(
                            hanab_game.ActionType.RankClue,
                            player % self.num_players,
                            rank
                        )
                for color in range(self.instance.variant.num_colors):
                    if self.instance.variant.color_touches(card, color):
                        return hanab_game.Action(
                            hanab_game.ActionType.ColorClue,
                            player % self.num_players,
                            color
                        )
        raise RuntimeError("Current game state did not permit any legal clue."
                           "This case is incredibly rare and currently not handled.")
