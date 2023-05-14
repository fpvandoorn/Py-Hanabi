from sat import solve_sat
from database import conn
from download_data import export_game
from variants import VARIANTS, variant_name
from alive_progress import alive_bar
from compress import decompress_deck, link
import concurrent.futures
from threading import Lock
from time import perf_counter
from greedy_solver import GameState, GreedyStrategy
from log_setup.logger_setup import logger
from deck_analyzer import analyze, InfeasibilityReason

MAX_PROCESSES=4

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
    cur = conn.cursor()
    cur2 = conn.cursor()
    cur.execute("SELECT seed FROM seeds WHERE deck is NULL")
    for (seed,) in cur:
        cur2.execute("SELECT id FROM games WHERE seed = (%s)", (seed,))
        (game_id,) = cur2.fetchone()
        print("Exporting game {} for seed {}.".format(game_id, seed))
        export_game(game_id)
        conn.commit()


def update_trivially_feasible_games():
    cur = conn.cursor()
    for var in VARIANTS:
        cur.execute("SELECT seed FROM seeds WHERE variant_id = (%s) AND feasible is null", (var['id'],))
        seeds = cur.fetchall()
        print('Checking variant {} (id {}), found {} seeds to check...'.format(var['name'], var['id'], len(seeds)))

        with alive_bar(total=len(seeds), title='{} ({})'.format(var['name'], var['id'])) as bar:
            for (seed,) in seeds:
                cur.execute("SELECT id, deck_plays, one_extra_card, one_less_card, all_or_nothing "
                            "FROM games WHERE score = (%s) AND seed = (%s) ORDER BY id;",
                            (5 * len(var['suits']), seed)
                )
                res = cur.fetchall()
                print("Checking seed {}: {:3} results".format(seed, len(res)))
                for (game_id, a, b, c, d) in res:
                    if None in [a,b,c,d]:
                        print('  Game {} not found in database, exporting...'.format(game_id))
                        succ, valid = export_game(game_id)
                        if not succ:
                            print('Error exporting game {}.'.format(game_id))
                            continue
                    else:
                        valid = not any([a,b,c,d])
                        print('  Game {} already in database, valid: {}'.format(game_id, valid))
                    if valid:
                        print('Seed {:10} (variant {} / {}) found to be feasible via game {:6}'.format(seed, var['id'], var['name'], game_id))
                        cur.execute("UPDATE seeds SET feasible = (%s) WHERE seed = (%s)", (True, seed))
                        conn.commit()
                        break
                    else:
                        print('  Cheaty game found')
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

def solve_instance(num_players, deck):
    # first, sanity check on running out of pace
    result = analyze(deck, num_players)
    if result is not None:
        assert type(result) == InfeasibilityReason
        logger.info("found infeasible deck")
        return False, None, None
    for num_remaining_cards in [0, 5, 10, 20, 30]:
#        logger.info("trying with {} remaining cards".format(num_remaining_cards))
        game = GameState(num_players, deck)
        strat = GreedyStrategy(game)

        # make a number of greedy moves
        while not game.is_over() and not game.is_known_lost():
            if num_remaining_cards != 0 and game.progress == game.deck_size - num_remaining_cards:
                break # stop solution here
            strat.make_move()
        
        # check if we won already
        if game.is_won():
#            print("won with greedy strat")
            return True, game, num_remaining_cards

        # now, apply sat solver
        if not game.is_over():
            logger.info("continuing greedy sol with SAT")
            solvable, sol = solve_sat(game)
            if solvable:
                return True, sol, num_remaining_cards
        logger.info("No success with {} remaining cards, reducing number of greedy moves, failed attempt was: {}".format(num_remaining_cards, link(game.to_json())))
#    print("Aborting trying with greedy strat")
    logger.info("Starting full SAT solver")
    game = GameState(num_players, deck)
    a, b = solve_sat(game)
    return a, b, 99


def solve_seed(seed, num_players, deck_compressed, var_id):
    try:
        deck = decompress_deck(deck_compressed)
        t0 = perf_counter()
        solvable, solution, num_remaining_cards = solve_instance(num_players, deck)
        t1 = perf_counter()
        logger.info("Solved instance {} in {} seconds".format(seed, round(t1-t0, 2)))

        mutex.acquire()
        if solvable is not None:
            lcur = conn.cursor()
            lcur.execute("UPDATE seeds SET feasible = (%s) WHERE seed = (%s)", (solvable, seed))
            conn.commit()

        if solvable == True:
            with open("remaining_cards.txt", "a") as f:
                f.write("Success with {} cards left in draw by greedy solver on seed {}: {}\n".format(num_remaining_cards, seed ,link(solution.to_json())))
        elif solvable == False:
            logger.info("seed {} was not solvable".format(seed))
            with open('infeasible_instances.txt', 'a') as f:
                f.write('{}-player, seed {:10}, {}\n'.format(num_players, seed, variant_name(var_id)))
        elif solvable is None:
            logger.info("seed {} skipped".format(seed))
        else:
            raise Exception("Programming Error")

        mutex.release()
    except Exception:
        traceback.format_exc()
        print("exception in subprocess:")


def solve_unknown_seeds():
    cur = conn.cursor()
    for var in VARIANTS:
        cur.execute("SELECT seed, num_players, deck FROM seeds WHERE variant_id = (%s) AND feasible IS NULL AND deck IS NOT NULL", (var['id'],))
        res = cur.fetchall()

#        for r in res:
#            solve_seed(r[0], r[1], r[2], var['id'])

        with concurrent.futures.ProcessPoolExecutor(max_workers=MAX_PROCESSES) as executor:
            fs = [executor.submit(solve_seed, r[0], r[1], r[2], var['id']) for r in res]
            with alive_bar(len(res), title='Seed solving on {}'.format(var['name'])) as bar:
                for f in concurrent.futures.as_completed(fs):
                    bar()
        break


solve_unknown_seeds()
