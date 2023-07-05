import enum
from typing import List, Optional
from hanabi import hanab_game

from hanabi.database.database import cur


def variant_id(name) -> Optional[int]:
    cur.execute(
        "SELECT id FROM variants WHERE name = %s",
        (name,)
    )
    var_id = cur.fetchone()
    if var_id is not None:
        return var_id[0]


def get_all_variant_ids() -> List[int]:
    cur.execute(
        "SELECT id FROM variants "
        "ORDER BY id"
    )
    return [var_id for (var_id,) in cur.fetchall()]


def variant_name(var_id) -> Optional[int]:
    cur.execute(
        "SELECT name FROM variants WHERE id = %s",
        (var_id,)
    )
    name = cur.fetchone()
    if name is not None:
        return name[0]


def num_suits(var_id) -> Optional[int]:
    cur.execute(
        "SELECT num_suits FROM variants WHERE id = %s",
        (var_id,)
    )
    num = cur.fetchone()
    if num is not None:
        return num


class ClueBehaviour(enum.Enum):
    none = 0
    default = 1
    all = 2


class Suit:
    def __init__(self, name, display_name, abbreviation, rank_clues, color_clues, prism, dark, rev, colors):
        self.name = name
        self.display_name = display_name
        self.abbreviation = abbreviation

        self.rank_clues = ClueBehaviour(rank_clues)
        self.color_clues = ClueBehaviour(color_clues)
        self.prism = prism

        self.dark = dark
        self.reversed = rev

        self.colors = colors

    def rank_touches(self, card_rank: int, clue_rank: int) -> bool:
        match self.rank_clues:
            case ClueBehaviour.none:
                return False
            case ClueBehaviour.default:
                return card_rank == clue_rank
            case ClueBehaviour.all:
                return True

    def color_touches(self, clue_color: int) -> bool:
        match self.color_clues:
            case ClueBehaviour.none:
                return False
            case ClueBehaviour.default:
                return clue_color in self.colors
            case ClueBehaviour.all:
                return True

    def __str__(self):
        return self.name

    def __repr__(self):
        return str(self.__dict__)

    @staticmethod
    def from_db(suit_id):
        cur.execute(
            "SELECT name, display_name, abbreviation, rank_clues, color_clues, prism, dark, reversed "
            "FROM suits "
            "WHERE id = %s",
            (suit_id,)
        )
        suit_properties = cur.fetchone()

        cur.execute(
            "SELECT color_id FROM suit_colors WHERE suit_id = %s",
            (suit_id,)
        )
        colors = list(map(lambda t: t[0], cur.fetchall()))
        return Suit(*suit_properties, colors)


class Variant:
    def __init__(
            self, name, clue_starved, throw_it_in_a_hole, alternating_clues, synesthesia, chimneys, funnels,
            no_color_clues, no_rank_clues, empty_color_clues, empty_rank_clues, odds_and_evens, up_or_down,
            critical_fours, special_rank, special_rank_ranks, special_rank_colors, special_deceptive, suits: List[Suit]
    ):
        self.name = name
        self.clue_starved = clue_starved
        self.throw_it_in_a_hole = throw_it_in_a_hole
        self.alternating_clues = alternating_clues  # TODO: has to be somehow supported by game itself
        self.synesthesia = synesthesia  #
        self.chimneys = chimneys  #
        self.funnels = funnels  #
        self.no_color_clues = no_color_clues  #
        self.no_rank_clues = no_rank_clues  #
        self.empty_color_clues = empty_color_clues  #
        self.empty_rank_clues = empty_rank_clues  #
        self.odds_and_evens = odds_and_evens  #
        self.up_or_down = up_or_down  # TODO: currently not supported
        self.critical_fours = critical_fours
        self.num_suits = len(suits)
        self.special_rank = special_rank  #
        self.special_rank_ranks = special_rank_ranks  #
        self.special_rank_colors = special_rank_colors  #
        self.special_deceptive = special_deceptive

        self.suits = suits
        self.colors = []

        if not self.no_color_clues:
            for suit in self.suits:
                for color in suit.colors:
                    if color not in self.colors:
                        self.colors.append(color)

        self.ranks = [1, 2, 3, 4, 5]
        if self.special_rank and self.special_rank_ranks != ClueBehaviour.default:
            self.ranks.remove(self.special_rank)
        if self.odds_and_evens:
            self.ranks = sorted([
                next(i for i in self.ranks if i % 2 == 0),
                next(i for i in self.ranks if i % 2 == 1)
                ]
            )
        if self.no_rank_clues or self.synesthesia:
            self.ranks = []

        self.num_colors = len(self.colors)

    def _preprocess_rank(self, value: int) -> List[int]:
        if self.empty_rank_clues:
            return []
        if self.chimneys:
            return [rank for rank in self.ranks if rank >= value]
        if self.funnels:
            return [rank for rank in self.ranks if rank <= value]
        if self.odds_and_evens:
            return [rank for rank in self.ranks if (rank - value) % 2 == 0]
        return [value]

    def _synesthesia_ranks(self, color_value: int) -> List[int]:
        return [rank for rank in self.ranks if (rank - color_value) % len(self.colors) == 0]

    def rank_touches(self, card: hanab_game.DeckCard, value: int):
        assert 0 <= card.suitIndex < self.num_suits,\
            f"Unexpected card {card}, suitIndex {card.suitIndex} out of bounds for {self.num_suits} suits."
        assert not self.no_rank_clues, "Cluing rank not allowed in this variant."
        assert value in self.ranks, f"Cluing value {value} not allowed in this variant."

        if self.special_rank is not None and self.special_rank_ranks != ClueBehaviour.default:
            suit = self.suits[card.suitIndex]
            match suit.rank_clues:
                case ClueBehaviour.none:
                    return False
                case ClueBehaviour.default:
                    match self.special_rank_ranks:
                        case ClueBehaviour.none:
                            return False
                        case ClueBehaviour.default:
                            assert False, "Programming error"
                        case ClueBehaviour.all:
                            return True
                case ClueBehaviour.all:
                    return True

        ranks = self._preprocess_rank(value)
        return any(self.suits[card.suitIndex].rank_touches(card.rank, rank) for rank in ranks)

    def color_touches(self, card: hanab_game.DeckCard, value: int):
        assert 0 <= card.suitIndex < self.num_suits, \
            f"Unexpected card {card}, suitIndex {card.suitIndex} out of bounds for {self.num_suits} suits."
        assert not self.no_color_clues, "Cluing color not allowed in this variant."
        assert 0 <= value < len(self.colors), f"Color clue with index {value} does not exist in this variant."

        if self.special_rank is not None and self.special_rank_colors != ClueBehaviour.default:
            suit = self.suits[card.suitIndex]
            match suit.color_clues:
                case ClueBehaviour.none:
                    return False
                case ClueBehaviour.default:
                    match self.special_rank_colors:
                        case ClueBehaviour.none:
                            return False
                        case ClueBehaviour.default:
                            assert False, "Programming error"
                        case ClueBehaviour.all:
                            return True
                case ClueBehaviour.all:
                    return True

        if self.empty_color_clues:
            return False
        if self.synesthesia and any(self.rank_touches(card, rank_val) for rank_val in self._synesthesia_ranks(value)):
            return True

        suit = self.suits[card.suitIndex]
        if suit.prism and value == ((card.rank - 1) % len(self.colors)):
            return True
        return suit.color_touches(self.colors[value])

    @property
    def max_score(self):
        return self.num_suits * 5

    @staticmethod
    def from_db(var_id):
        cur.execute(
            "SELECT "
            "name, clue_starved, throw_it_in_a_hole, alternating_clues, synesthesia, chimneys, funnels, "
            "no_color_clues, no_rank_clues, empty_color_clues, empty_rank_clues, odds_and_evens, up_or_down,"
            "critical_fours, special_rank, special_rank_ranks, special_rank_colors, special_deceptive "
            "FROM variants WHERE id = %s",
            (var_id,)
        )
        var_properties = cur.fetchone()

        cur.execute(
            "SELECT suit_id FROM variant_suits "
            "WHERE variant_id = %s "
            "ORDER BY index",
            (var_id,)
        )
        var_suits = [Suit.from_db(*s) for s in cur.fetchall()]

        return Variant(*var_properties, var_suits)
