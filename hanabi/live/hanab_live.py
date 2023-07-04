from typing import List

import hanabi
from hanabi import constants
from hanabi.live.variants import Variant


class HanabLiveInstance(hanabi.HanabiInstance):
    def __init__(
            self,
            deck: List[hanabi.DeckCard],
            num_players: int,
            variant_id: int,
            one_extra_card: bool = False,
            one_less_card: bool = False,
            *args, **kwargs
    ):
        assert 2 <= num_players <= 6
        hand_size = constants.HAND_SIZES[num_players]
        if one_less_card:
            hand_size -= 1
        if one_extra_card:
            hand_size += 1

        super().__init__(deck, num_players, hand_size=hand_size, *args, **kwargs)
        self.variant_id = variant_id
        self.variant = Variant.from_db(self.variant_id)

    @staticmethod
    def select_standard_variant_id(instance: hanabi.HanabiInstance):
        err_msg = "Hanabi instance not supported by hanab.live, cannot convert to HanabLiveInstance: "
        assert 3 <= instance.num_suits <= 6, \
            err_msg + "Illegal number of suits ({}) found, must be in range [3,6]".format(instance.num_suits)
        assert 0 <= instance.num_dark_suits <= 2, \
            err_msg + "Illegal number of dark suits ({}) found, must be in range [0,2]".format(instance.num_dark_suits)
        assert 4 <= instance.num_suits - instance.num_dark_suits, \
            err_msg + "Illegal ratio of dark suits to suits, can have at most {} dark suits with {} total suits".format(
                max(instance.num_suits - 4, 0), instance.num_suits
            )
        return constants.VARIANT_IDS_STANDARD_DISTRIBUTIONS[instance.num_suits][instance.num_dark_suits]


class HanabLiveGameState(hanabi.GameState):
    def __init__(self, instance: HanabLiveInstance, starting_player: int = 0):
        super().__init__(instance, starting_player)
        self.instance: HanabLiveInstance = instance

    def make_action(self, action):
        match action.type:
            case hanabi.ActionType.ColorClue | hanabi.ActionType.RankClue:
                assert(self.clues > 0)
                self.actions.append(action)
                self.clues -= self.instance.clue_increment
                self._make_turn()
                # TODO: could check that the clue specified is in fact legal
            case hanabi.ActionType.Play:
                self.play(action.target)
            case hanabi.ActionType.Discard:
                self.discard(action.target)
            case hanabi.ActionType.EndGame | hanabi.ActionType.VoteTerminate:
                self.over = True

    def _waste_clue(self) -> hanabi.Action:
        for player in range(self.turn + 1, self.turn + self.num_players):
            for card in self.hands[player % self.num_players]:
                for rank in self.instance.variant.ranks:
                    if self.instance.variant.rank_touches(card, rank):
                        return hanabi.Action(
                            hanabi.ActionType.RankClue,
                            player % self.num_players,
                            rank
                        )
                for color in range(self.instance.variant.num_colors):
                    if self.instance.variant.color_touches(card, color):
                        return hanabi.Action(
                            hanabi.ActionType.ColorClue,
                            player % self.num_players,
                            color
                        )
        raise RuntimeError("Current game state did not permit any legal clue."
                           "This case is incredibly rare and currently not handled.")
