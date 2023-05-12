import enum
from typing import List
from hanabi import DeckCard, ActionType

from database import cur


def variant_id(name):
    cur.execute(
        "SELECT id FROM variants WHERE name = %s",
        (name,)
    )
    return cur.fetchone()[0]


def variant_name(var_id):
    cur.execute(
        "SELECT name FROM variants WHERE id = %s",
        (var_id,)
    )
    return cur.fetchone()[0]


def num_suits(var_id):
    cur.execute(
        "SELECT num_suits FROM variants WHERE id = %s",
        (var_id,)
    )
    return cur.fetchone()[0]


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
        self.alternating_clues = alternating_clues
        self.synesthesia = synesthesia
        self.chimneys = chimneys
        self.funnels = funnels
        self.no_color_clues = no_color_clues
        self.no_rank_clues = no_rank_clues
        self.empty_color_clues = empty_color_clues
        self.empty_rank_clues = empty_rank_clues
        self.odds_and_evens = odds_and_evens
        self.up_or_down = up_or_down
        self.critical_fours = critical_fours
        self.num_suits = len(suits)
        self.special_rank = special_rank
        self.special_rank_ranks = special_rank_ranks
        self.special_rank_colors = special_rank_colors
        self.special_deceptive = special_deceptive

        self.suits = suits
        self.colors = []

        if not self.no_color_clues:
            for suit in self.suits:
                for color in suit.colors:
                    if color not in self.colors:
                        self.colors.append(color)

        self.num_colors = len(self.colors)

    def rank_touches(self, card: DeckCard, value: int):
        pass

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
