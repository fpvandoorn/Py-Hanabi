import json
import os
import networkx as nx
from collections import OrderedDict
import matplotlib.pyplot as plt

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


class Variant:
    def __init__(
            self, name, clue_starved, throw_it_in_a_hole, alternating_clues, synesthesia, chimneys, funnels,
            no_color_clues, no_rank_clues, odds_and_evens, up_or_down, critical_fours, num_suits, special_rank,
            special_rank_ranks, special_rank_colors, suits
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
        self.odds_and_evens = odds_and_evens
        self.up_or_down = up_or_down
        self.critical_fours = critical_fours
        self.num_suits = num_suits
        self.special_rank = special_rank
        self.special_rank_ranks = special_rank_ranks
        self.special_rank_colors = special_rank_colors

        self.suits = suits

    @staticmethod
    def from_db(var_id):
        cur.execute(
            "SELECT "
            "name, clue_starved, throw_it_in_a_hole, alternating_clues, synesthesia, chimneys, funnels, "
            "no_color_clues, no_rank_clues, odds_and_evens, up_or_down, critical_fours, num_suits, special_rank, "
            "special_rank_ranks, special_rank_colors "
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
        var_suits = list(map(lambda x: x[0], cur.fetchall()))

        return Variant(*var_properties, var_suits)
