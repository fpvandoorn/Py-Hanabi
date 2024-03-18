from typing import Optional
import pebble.concurrent
import concurrent.futures

import traceback
import alive_progress
import threading
import time

from hanabi import logger
from hanabi.solvers.sat import solve_sat
from hanabi import database
from hanabi.live import download_data
from hanabi.live import compress
from hanabi import hanab_game
from hanabi.solvers import greedy_solver
from hanabi.solvers import deck_analyzer
from hanabi.live import variants

MAX_PROCESSES = 6


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


mutex = threading.Lock()


def solve_instance(instance: hanab_game.HanabiInstance):
    # first, sanity check on running out of pace
    result = deck_analyzer.analyze(instance)
    if len(result) != 0:
        logger.info("found infeasible deck by foreward analysis")
        return False, None, None
    for num_remaining_cards in [0, 20]:
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
            #            print("won with greedy strat")
            return True, game, num_remaining_cards

        # now, apply sat solver
        if not game.is_over():
            logger.debug("continuing greedy sol with SAT")
            solvable, sol = solve_sat(game)
            if solvable is None:
                return True, sol, num_remaining_cards
        logger.debug(
            "No success with {} remaining cards, reducing number of greedy moves, failed attempt was: {}".format(
                num_remaining_cards, compress.link(game)))
    #    print("Aborting trying with greedy strat")
    logger.debug("Starting full SAT solver")
    game = hanab_game.GameState(instance)
    a, b = solve_sat(game)
    return a, b, instance.draw_pile_size


@pebble.concurrent.process(timeout=150)
def solve_seed_with_timeout(seed, num_players, deck_compressed, var_name: Optional[str] = None):
    try:
        logger.verbose("Starting to solve seed {}".format(seed))
        deck = compress.decompress_deck(deck_compressed)
        t0 = time.perf_counter()
        solvable, solution, num_remaining_cards = solve_instance(hanab_game.HanabiInstance(deck, num_players))
        t1 = time.perf_counter()
        logger.verbose("Solved instance {} in {} seconds: {}".format(seed, round(t1 - t0, 2), solvable))

        mutex.acquire()
        if solvable is not None:
            database.cur.execute("UPDATE seeds SET feasible = (%s) WHERE seed = (%s)", (solvable, seed))
            database.conn.commit()
        mutex.release()

        if solvable == True:
            logger.verbose("Success with {} cards left in draw by greedy solver on seed {}: {}\n".format(
                num_remaining_cards, seed, compress.link(solution))
            )
        elif solvable == False:
            logger.debug("seed {} was not solvable".format(seed))
            logger.debug('{}-player, seed {:10}, {}\n'.format(num_players, seed, var_name))
        elif solvable is None:
            logger.verbose("seed {} skipped".format(seed))
        else:
            raise Exception("Programming Error")

    except Exception as e:
        print("exception in subprocess:")
        traceback.print_exc()


def solve_seed(seed, num_players, deck_compressed, var_name: Optional[str] = None):
    f = solve_seed_with_timeout(seed, num_players, deck_compressed, var_name)
    try:
        return f.result()
    except TimeoutError:
        logger.verbose("Solving on seed {} timed out".format(seed))
        return


def solve_unknown_seeds(variant_id, variant_name: Optional[str] = None):
    database.cur.execute(
        "SELECT seed, num_players, deck FROM seeds WHERE variant_id = (%s) AND feasible IS NULL",
        (variant_id,)
    )
    res = database.cur.fetchall()

    with concurrent.futures.ProcessPoolExecutor(max_workers=MAX_PROCESSES) as executor:
        fs = [executor.submit(solve_seed, r[0], r[1], r[2], variant_name) for r in res]
        with alive_progress.alive_bar(len(res), title='Seed solving on {}'.format(variant_name)) as bar:
            for f in concurrent.futures.as_completed(fs):
                bar()
