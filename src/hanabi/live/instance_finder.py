from dataclasses import dataclass
from types import NoneType
from typing import Optional, Tuple, List
import pebble.concurrent
import concurrent.futures

import traceback
import alive_progress
import threading
import time

import psycopg2.extras

import hanabi.hanab_game
from hanabi import logger
from hanabi.hanab_game import GameState
from hanabi.solvers.sat import solve_sat
from hanabi import database
from hanabi.live import download_data
from hanabi.live import compress
from hanabi import hanab_game
from hanabi.solvers import greedy_solver
from hanabi.solvers import deck_analyzer
from hanabi.live import variants
from hanabi.database.games_db_interface import store_actions

MAX_PROCESSES = 3


def update_trivially_feasible_games(variant_id):
    variant: variants.Variant = variants.Variant.from_db(variant_id)
    database.cur.execute("SELECT seed FROM seeds WHERE variant_id = (%s) AND feasible is null", (variant_id,))
    seeds = database.cur.fetchall()
    logger.verbose('Checking variant {} (id {}), found {} seeds to check...'.format(variant.name, variant_id, len(seeds)))

    with alive_progress.alive_bar(total=len(seeds), title='{} ({})'.format(variant.name, variant_id)) as bar:
        for (seed,) in seeds:
            database.cur.execute(
                "SELECT id, deck_plays, one_extra_card, one_less_card, all_or_nothing, detrimental_characters "
                "FROM games WHERE score = (%s) AND seed = (%s) ORDER BY id;",
                (variant.max_score, seed)
            )
            res = database.cur.fetchall()
            logger.debug("Checking seed {}: {:3} results".format(seed, len(res)))
            for (game_id, a, b, c, d, e) in res:
                if None in [a, b, c, d, e]:
                    logger.debug('  Game {} not found in database, exporting...'.format(game_id))
                    download_data.detailed_export_game(
                        game_id, var_id=variant_id, score=variant.max_score, seed_exists=True
                    )
                    database.cur.execute("SELECT deck_plays, one_extra_card, one_less_card, all_or_nothing, "
                                         "detrimental_characters "
                                         "FROM games WHERE id = (%s)",
                                         (game_id,))
                    (a, b, c, d, e) = database.cur.fetchone()
                else:
                    logger.debug('  Game {} already in database'.format(game_id))
                valid = not any([a, b, c, d, e])
                if valid:
                    print(a, b, c, d, e)
                    logger.verbose(
                        'Seed {:10} (variant {}) found to be feasible via game {:6}'.format(seed, variant_id, game_id))
                    database.cur.execute("UPDATE seeds SET (feasible, max_score_theoretical) = (%s, %s) WHERE seed = "
                                         "(%s)", (True, variant.max_score, seed))
                    database.cur.execute(
                        "INSERT INTO score_lower_bounds (seed, score_lower_bound, game_id) VALUES (%s, %s, %s)",
                        (seed, variant.max_score, game_id)
                    )
                    database.conn.commit()
                    break
                else:
                    logger.verbose('  Cheaty game {} found'.format(game_id))
            bar()


def get_decks_for_all_seeds():
    cur = database.conn.database.cursor()
    cur.execute("SELECT id "
                "FROM games "
                "  INNER JOIN seeds "
                "  ON seeds.seed = games.seed"
                "    WHERE"
                "      seeds.deck is null"
                "      AND"
                "      games.id = ("
                "         SELECT id FROM games WHERE games.seed = seeds.seed LIMIT 1"
                "     )"
                )
    print("Exporting decks for all seeds")
    res = cur.fetchall()
    with alive_progress.alive_bar(len(res), title="Exporting decks") as bar:
        for (game_id,) in res:
            download_data.detailed_export_game(game_id)
            bar()


@dataclass
class SolutionData:
    infeasibility_reasons: Optional[List[deck_analyzer.InfeasibilityReason]]
    seed: str = None
    time_ms: int = 0
    feasible: Optional[bool] = None
    solution: Optional[GameState] = None
    num_remaining_cards: Optional[int] = None
    skipped: bool = False

    def __init__(self):
        self.infeasibility_reasons = []


def solve_instance(instance: hanab_game.HanabiInstance, list_all_pace_cuts: bool = False)-> SolutionData:
    retval = SolutionData()
    # first, sanity check on running out of pace
    result = deck_analyzer.analyze(instance, list_all_pace_cuts=list_all_pace_cuts)
    if len(result.infeasibility_reasons) != 0:
        logger.verbose("found infeasible deck by preliminary analysis")
        retval.feasible = False
        retval.infeasibility_reasons = result.infeasibility_reasons
        return retval
    for num_remaining_cards in [0, 10, 20]:
        #        logger.info("trying with {} remaining cards".format(num_remaining_cards))
        game = hanab_game.GameState(instance)
        strat = greedy_solver.GreedyStrategy(game)

        # make a number of greedy moves
        while not game.is_over() and not game.is_known_lost():
            if num_remaining_cards != 0 and game.progress == game.deck_size - num_remaining_cards:
                break  # stop solution here
            strat.make_move()

        # check if we won already
        if game.is_won():
            retval.feasible = True
            retval.solution = game
            retval.num_remaining_cards = num_remaining_cards
            #            print("won with greedy strat")
            return retval

        # now, apply sat solver
        if not game.is_over():
            logger.debug("continuing greedy sol with SAT")
            solvable, solution = solve_sat(game)
            if solvable:
                retval.feasible = True
                retval.solution = solution
                retval.num_remaining_cards = num_remaining_cards
                return retval
        logger.debug(
            "No success with {} remaining cards, reducing number of greedy moves, failed attempt was: {}".format(
                num_remaining_cards, compress.link(game)))

    logger.debug("Starting full SAT solver")

    game = hanab_game.GameState(instance)
    retval.feasible, retval.solution = solve_sat(game)
    retval.num_remaining_cards = instance.draw_pile_size
    if not retval.feasible:
        assert len(retval.infeasibility_reasons) == 0
        retval.infeasibility_reasons.append(deck_analyzer.InfeasibilityReason(deck_analyzer.InfeasibilityType.SAT))
    return retval



def solve_seed(seed, num_players, deck, list_all_pace_cuts: bool = False, timeout: Optional[int] = 150) -> SolutionData:
    try:
        @pebble.concurrent.process(timeout=timeout)
        def solve_seed_with_timeout(seed, num_players, deck) -> SolutionData:
            try:
                logger.verbose("Starting to solve seed {}".format(seed))

                t0 = time.perf_counter()
                retval = solve_instance(hanab_game.HanabiInstance(deck, num_players), list_all_pace_cuts=list_all_pace_cuts)
                t1 = time.perf_counter()

                retval.seed = seed
                retval.time_ms = round((t1 - t0) * 1000)
                logger.verbose("Solved instance {} in {} seconds: {}".format(seed, round(t1 - t0, 2), retval.feasible))
                return retval

            except Exception as e:
                print("exception in subprocess:")
                traceback.print_exc()

        f = solve_seed_with_timeout(seed, num_players, deck)
        try:
            return f.result()
        except TimeoutError:
            retval = SolutionData()
            retval.seed = seed
            retval.feasible = None
            retval.time_ms = 1000 * timeout
            logger.verbose("Solving on seed {} timed out".format(seed))
            return retval
    except Exception as e:
        print("exception in subprocess:")
        traceback.print_exc()

def replace_none_with_zero(x):
    if x is None:
        return 0
    else:
        return x


def process_solve_result(result: SolutionData):
    if result.feasible is not None:
        database.cur.execute("UPDATE seeds SET (feasible, solve_time_ms) = (%s, %s) WHERE seed = (%s)",
                             (result.feasible, result.time_ms, result.seed))
        if result.feasible:
            assert result.solution is not None
            database.cur.execute("INSERT INTO certificate_games (seed, num_turns) "
                                 "VALUES (%s, %s) "
                                 "RETURNING ID ", (result.seed, len(result.solution.actions)))
            game_id = database.cur.fetchone()[0]
            store_actions(game_id, result.solution.actions, True)
            logger.verbose("Success with {} cards left in draw by greedy solver on seed {}: {}\n".format(
                result.num_remaining_cards, result.seed, compress.link(result.solution))
            )
        else:
            logger.debug("seed {} was not solvable".format(result.seed))
            vals = [(result.seed, reason.type.value, replace_none_with_zero(reason.index), replace_none_with_zero(reason.value)) for reason in result.infeasibility_reasons]
            psycopg2.extras.execute_values(
                database.cur,
                "INSERT INTO infeasibility_reasons (seed, reason, index, value) "
                "VALUES %s "
                "ON CONFLICT (seed, reason, index) DO NOTHING",
                vals
            )
            database.conn.commit()
    elif result.skipped:
        logger.verbose("seed {} skipped".format(result.seed))
    else:
        database.cur.execute("UPDATE seeds SET solve_time_ms = %s WHERE seed = (%s)", (result.time_ms, result.seed))
    database.conn.commit()


def solve_unknown_seeds(variant_id, seed_class: int = 0, num_players: Optional[int] = None, list_all_pace_cuts: bool = False, timeout: Optional[int] = 150, num_threads: int = 4):
    variant_name = variants.variant_name(variant_id)
    query = "SELECT seeds.seed, num_players, array_agg(suit_index order by deck_index asc), array_agg(rank order by deck_index asc) "\
            "FROM seeds "\
            "INNER JOIN decks ON seeds.seed = decks.seed "\
            "WHERE variant_id = (%s) "\
            "AND class = (%s) "\
            "AND feasible IS NULL "\
            "AND solve_time_ms < (%s)"
    if num_players is not None:
        query += "AND num_players = {} ".format(num_players)
    query += "GROUP BY seeds.seed ORDER BY num"
    database.cur.execute(query,
        (variant_id, seed_class, 1000 * timeout)
    )
    res = database.cur.fetchall()
    data = []
    for (seed, num_players, suits, ranks) in res:
        assert len(suits) == len(ranks)
        deck = []
        for (suit, rank) in zip(suits, ranks):
            deck.append(hanabi.hanab_game.DeckCard(suit, rank))
        data.append((seed, num_players, deck))

    """
    with alive_progress.alive_bar(len(res), title='Seed solving on {}'.format(variant_name)) as bar:
        for d in data:
            solve_seed(d[0], d[1], d[2], timeout)
            bar()
    return
    """


    with concurrent.futures.ProcessPoolExecutor(max_workers=num_threads) as executor:
        fs = [executor.submit(solve_seed, d[0], d[1], d[2], list_all_pace_cuts, timeout) for d in data]
        with alive_progress.alive_bar(len(res), title='Seed solving on {}'.format(variant_name)) as bar:
            for f in concurrent.futures.as_completed(fs):
                result = f.result()
                process_solve_result(result)
                bar()