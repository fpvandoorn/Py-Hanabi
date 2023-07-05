import json
import requests
from pathlib import Path

import platformdirs

from hanabi import logger
from hanabi import constants
from .database import cur, conn


def get_existing_tables():
    cur.execute(
        "   SELECT tablename FROM pg_tables"
        "   WHERE"
        "       schemaname = 'public' AND "
        "       tablename IN ("
        "           'seeds',"
        "           'games',"
        "           'suits',"
        "           'colors',"
        "           'suit_colors',"
        "           'variants',"
        "           'variant_suits',"
        "           'variant_game_downloads'"
        "       )"
    )
    return [table for (table,) in cur.fetchall()]


def init_database_tables():
    this = Path(__file__)
    logger.verbose("Initialising games and seeds tables...")
    with open(this.parent / "games_seeds_schema.sql") as f:
        cur.execute(f.read())
    logger.verbose("Successfully initialised games and seeds tables.")

    logger.verbose("Initialising variants, colors and suits tables...")
    with open(this.parent / "variant_suits_schema.sql", "r") as f:
        cur.execute(f.read())
    logger.verbose("Successfully initialised variants, colors and suits tables...")

    conn.commit()


def populate_static_tables():
    _populate_static_tables(*_download_json_files())


def _populate_static_tables(suits, variants):
    logger.verbose("Populating static tables with hanab.live format information")
    suits_to_reverse = set()
    for var in variants:
        for suit in var['suits']:
            if 'Reversed' in suit:
                suits_to_reverse.add(suit.replace(' Reversed', ''))

    _populate_suits(suits, suits_to_reverse)
    _populate_variants(variants)

    conn.commit()


def _populate_suits(suits, suits_to_reverse):
    logger.verbose("Populating suits and colors tables...")
    logger.debug("Needing to reverse the following suits: {}".format(suits_to_reverse))
    for suit in suits:
        name: str = suit['name']
        display_name: str = suit.get('displayName', name)
        abbreviation = suit.get('abbreviation', name[0].upper())

        all_colors = suit.get('allClueColors', False)
        no_color_clues = suit.get('noClueColors', False)
        all_ranks = suit.get('allClueRanks', False)
        no_rank_clues = suit.get('noClueRanks', False)
        prism = suit.get('prism', False)
        dark = suit.get('oneOfEach', False)

        assert([all_colors, no_color_clues, prism].count(True) <= 1)
        assert(not all([no_rank_clues, all_ranks]))

        color_clues = 2 if all_colors else (0 if no_color_clues else 1)
        rank_clues = 2 if all_ranks else (0 if no_rank_clues else 1)

        clue_colors = suit.get('clueColors', [name] if (color_clues == 1 and not prism) else [])

        for rev in [False, True]:
            if rev is True and name not in suits_to_reverse:
                break
            suit_name = name
            suit_name += ' Reversed' if rev else ''
            cur.execute(
                "INSERT INTO suits (name, display_name, abbreviation, rank_clues, color_clues, dark, reversed, prism)"
                "VALUES"
                "(%s, %s, %s, %s, %s, %s, %s, %s)",
                (suit_name, display_name, abbreviation, rank_clues, color_clues, dark, rev, prism)
            )
            logger.debug("New suit {} imported.".format(name))
            cur.execute(
                "SELECT id FROM suits WHERE name = %s",
                (suit_name,)
            )
            suit_id = cur.fetchone()

            for color in clue_colors:
                if not rev:
                    cur.execute(
                        "INSERT INTO colors (name) VALUES (%s)"
                        "ON CONFLICT (name) DO NOTHING",
                        (color,)
                    )
                    logger.debug("New clue color {} imported.".format(color))
                cur.execute(
                    "SELECT id FROM colors WHERE name = %s",
                    (color,)
                )
                color_id = cur.fetchone()

                cur.execute(
                    "INSERT INTO suit_colors (suit_id, color_id) VALUES"
                    "(%s, %s)",
                    (suit_id, color_id)
                )


def _populate_variants(variants):
    logger.verbose("Populating variants table...")
    for var in variants:
        var_id = var['id']
        name = var['name']
        clue_starved = var.get('clueStarved', False)
        throw_it_in_a_hole = var.get('throwItInHole', False)
        alternating_clues = var.get('alternatingClues', False)
        synesthesia = var.get('synesthesia', False)
        chimneys = var.get('chimneys', False)
        funnels = var.get('funnels', False)
        no_color_clues = var.get('clueColors', None) == []
        no_rank_clues = var.get('clueRanks', None) == []
        empty_color_clues = var.get('colorCluesTouchNothing', False)
        empty_rank_clues = var.get('rankCluesTouchNothing', False)
        odds_and_evens = var.get('oddsAndEvens', False)
        up_or_down = var.get('upOrDown', False)
        critical_fours = var.get('criticalFours', False)
        suits = var['suits']
        num_suits = len(suits)
        special_rank_no_ranks = var.get('specialNoClueRanks', False)
        special_rank_all_ranks = var.get('specialAllClueRanks', False)
        special_rank_no_colors = var.get('specialNoClueColors', False)
        special_rank_all_colors = var.get('specialAllClueColors', False)
        special_rank = var.get('specialRank', None)
        special_deceptive = var.get('specialDeceptive', False)

        assert(not all([special_rank_all_ranks, special_rank_no_ranks]))
        assert(not all([special_rank_all_colors, special_rank_no_colors]))

        special_rank_ranks = 2 if special_rank_all_ranks else (0 if special_rank_no_ranks else 1)
        special_rank_colors = 2 if special_rank_all_colors else (0 if special_rank_no_colors else 1)

        cur.execute(
            "INSERT INTO variants ("
            "id, name, clue_starved, throw_it_in_a_hole, alternating_clues, synesthesia, chimneys, funnels,"
            "no_color_clues, no_rank_clues, empty_color_clues, empty_rank_clues, odds_and_evens, up_or_down,"
            "critical_fours, num_suits, special_rank, special_rank_ranks, special_rank_colors, special_deceptive"
            ")"
            "VALUES"
            "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                var_id, name, clue_starved, throw_it_in_a_hole, alternating_clues, synesthesia, chimneys, funnels,
                no_color_clues, no_rank_clues, empty_color_clues, empty_rank_clues, odds_and_evens, up_or_down,
                critical_fours, num_suits, special_rank, special_rank_ranks, special_rank_colors, special_deceptive
            )
        )

        for index, suit in enumerate(suits):
            cur.execute(
                "SELECT id FROM suits WHERE name = %s",
                (suit,)
            )
            suit_id = cur.fetchone()
            if suit_id is None:
                err_msg = "Invalid suit name {} encountered while importing variant {} [{}]." \
                          "Is the suits DB not populated?"\
                    .format(suit, var_id, name)
                logger.error(err_msg)
                raise RuntimeError(err_msg)

            cur.execute(
                "INSERT INTO variant_suits (variant_id, suit_id, index) VALUES (%s, %s, %s)",
                (var_id, suit_id, index)
            )


def _download_json_files():
    logger.verbose("Downloading JSON files for suits and variants from github...")
    base_url = "https://raw.githubusercontent.com/Hanabi-Live/hanabi-live/main/packages/data/src/json"
    cache_dir = Path(platformdirs.user_cache_dir(constants.APP_NAME))
    cache_dir.mkdir(parents=True, exist_ok=True)
    data = {}
    for name in ["suits", "variants"]:
        file = (cache_dir / name).with_suffix(".json")
        if file.exists():
            data[name] = json.loads(file.read_text())
            continue
        url = base_url + "/" + file.name
        print("foo")
        response = requests.get(url)
        if not response.status_code == 200:
            err_msg = "Could not download initialization file {} from github (tried url {})".format(filename, url)
            logger.error(err_msg)
            raise RuntimeError(err_msg)
        file.write_text(response.text)
        data[name] = json.loads(response.text)
    return data['suits'], data['variants']
