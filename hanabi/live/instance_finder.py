from typing import Optional
import pebble.concurrent
import concurrent.futures

import traceback

from sat import solve_sat
from hanabi.database.database import conn, cur
from hanabi.live.download_data import detailed_export_game
from alive_progress import alive_bar
from hanabi.live.compress import decompress_deck, link
from hanabi import HanabiInstance
from threading import Lock
from time import perf_counter
from greedy_solver import GameState, GreedyStrategy
from hanabi.log_setup import logger
from deck_analyzer import analyze, InfeasibilityReason
from hanabi.live.variants import Variant

MAX_PROCESSES = 6


def update_seeds_db():
    cur2 = conn.cursor()
    with conn.cursor() as cur:
        cur.execute("SELECT num_players, seed, variant_id from games;")
        for (num_players, seed, variant_id) in cur:
            cur2.execute("SELECT COUNT(*) from seeds WHERE seed = (%s);", (seed,))
            if cur2.fetchone()[0] == 0:
                print("new seed {}".format(seed))
                cur2.execute("INSERT INTO seeds"
                             "(seed, num_players, variant_id)"
                             "VALUES"
                             "(%s, %s, %s)",
                             (seed, num_players, variant_id)
                             )
                conn.commit()
            else:
                print("seed {} already found in DB".format(seed))


def get_decks_of_seeds():
    cur2 = conn.cursor()
    cur.execute("SELECT seed, variant_id FROM seeds WHERE deck is NULL")
    for (seed, variant_id) in cur:
        cur2.execute("SELECT id FROM games WHERE seed = (%s) LIMIT 1", (seed,))
        (game_id,) = cur2.fetchone()
        logger.verbose("Exporting game {} for seed {}.".format(game_id, seed))
        detailed_export_game(game_id, var_id=variant_id, seed_exists=True)
        conn.commit()


def update_trivially_feasible_games(variant_id):
    variant: Variant = Variant.from_db(variant_id)
    cur.execute("SELECT seed FROM seeds WHERE variant_id = (%s) AND feasible is null", (variant_id,))
    seeds = cur.fetchall()
    print('Checking variant {} (id {}), found {} seeds to check...'.format(variant.name, variant_id, len(seeds)))

    with alive_bar(total=len(seeds), title='{} ({})'.format(variant.name, variant_id)) as bar:
        for (seed,) in seeds:
            cur.execute("SELECT id, deck_plays, one_extra_card, one_less_card, all_or_nothing "
                        "FROM games WHERE score = (%s) AND seed = (%s) ORDER BY id;",
                        (variant.max_score, seed)
                        )
            res = cur.fetchall()
            logger.debug("Checking seed {}: {:3} results".format(seed, len(res)))
            for (game_id, a, b, c, d) in res:
                if None in [a, b, c, d]:
                    logger.debug('  Game {} not found in database, exporting...'.format(game_id))
                    detailed_export_game(game_id, var_id=variant_id)
                else:
                    logger.debug('  Game {} already in database'.format(game_id, valid))
                valid = not any([a, b, c, d])
                if valid:
                    logger.verbose('Seed {:10} (variant {}) found to be feasible via game {:6}'.format(seed, variant_id, game_id))
                    cur.execute("UPDATE seeds SET feasible = (%s) WHERE seed = (%s)", (True, seed))
                    conn.commit()
                    break
                else:
                    logger.verbose('  Cheaty game found')
            bar()


def get_decks_for_all_seeds():
    cur = conn.cursor()
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
    with alive_bar(len(res), title="Exporting decks") as bar:
        for (game_id,) in res:
            export_game(game_id)
            bar()


mutex = Lock()


def solve_instance(instance: HanabiInstance):
    # first, sanity check on running out of pace
    result = analyze(instance)
    if result is not None:
        assert type(result) == InfeasibilityReason
        logger.debug("found infeasible deck")
        return False, None, None
    for num_remaining_cards in [0, 20]:
        #        logger.info("trying with {} remaining cards".format(num_remaining_cards))
        game = GameState(instance)
        strat = GreedyStrategy(game)

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
                num_remaining_cards, link(game)))
    #    print("Aborting trying with greedy strat")
    logger.debug("Starting full SAT solver")
    game = GameState(instance)
    a, b = solve_sat(game)
    return a, b, instance.draw_pile_size


@pebble.concurrent.process(timeout=150)
def solve_seed_with_timeout(seed, num_players, deck_compressed, var_name: Optional[str] = None):
    try:
        logger.verbose("Starting to solve seed {}".format(seed))
        deck = decompress_deck(deck_compressed)
        t0 = perf_counter()
        solvable, solution, num_remaining_cards = solve_instance(HanabiInstance(deck, num_players))
        t1 = perf_counter()
        logger.verbose("Solved instance {} in {} seconds: {}".format(seed, round(t1 - t0, 2), solvable))

        mutex.acquire()
        if solvable is not None:
            cur.execute("UPDATE seeds SET feasible = (%s) WHERE seed = (%s)", (solvable, seed))
            conn.commit()
        mutex.release()

        if solvable == True:
            logger.verbose("Success with {} cards left in draw by greedy solver on seed {}: {}\n".format(
                num_remaining_cards, seed, link(solution))
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
    cur.execute("SELECT seed, num_players, deck FROM seeds WHERE variant_id = (%s) AND feasible IS NULL", (variant_id,))
    res = cur.fetchall()

    #    for r in res:
    #        solve_seed(r[0], r[1], r[2], variant_name)

    with concurrent.futures.ProcessPoolExecutor(max_workers=MAX_PROCESSES) as executor:
        fs = [executor.submit(solve_seed, r[0], r[1], r[2], variant_name) for r in res]
        with alive_bar(len(res), title='Seed solving on {}'.format(variant_name)) as bar:
            for f in concurrent.futures.as_completed(fs):
                bar()


update_trivially_feasible_games(0)
solve_unknown_seeds(0, "No Variant")