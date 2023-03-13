import json
from time import sleep
from site_api import get, api, replay
from sat import COLORS, solve
from database import Game, store, load, commit, conn
from download_data import export_game
from variants import num_suits, VARIANTS
from alive_progress import alive_bar
from compress import decompress_deck
import concurrent.futures
from threading import Lock
from time import sleep


MAX_PROCESSES=6

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
                        print('Seed {:9} (variant {} / {}) found to be feasible via game {:6}'.format(seed, var['id'], var['name'], game_id))
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

def solve_seed(seed, num_players, deck_compressed):
    deck = decompress_deck(deck_compressed)
    solvable, solution = solve(deck, num_players)

    mutex.acquire()
    lcur = conn.cursor()
    lcur.execute("UPDATE seeds SET feasible = (%s) WHERE seed = (%s)", (solvable, seed))
    conn.commit()

    if not solvable:
        with open('unsolvable_seeds', 'a') as f:
            f.write('{}-player, seed {}\n'.format(num_players, seed))
#        print('Seed {} ({} players) not solvable: {}'.format(seed, num_players, deck))

    mutex.release()


def solve_unknown_seeds():
    cur = conn.cursor()
    for var in VARIANTS:
        cur.execute("SELECT seed, num_players, deck FROM seeds WHERE variant_id = (%s) AND feasible IS NULL AND deck IS NOT NULL ORDER BY num_players DESC", (var['id'],))
        res = cur.fetchall()

        with concurrent.futures.ProcessPoolExecutor(max_workers=MAX_PROCESSES) as executor:
            fs = [executor.submit(solve_seed, *r) for r in res]
            with alive_bar(len(res), title='Seed solving on {}'.format(var['name'])) as bar:
                for f in concurrent.futures.as_completed(fs):
                    bar()
        break


solve_unknown_seeds()
exit(0)


print('looked at {} games'.format(num_games))
for i in range(2,7):
    print("Found {} seeds in {}-player in database".format(len(seeds[i]), i))

hard_seeds = []
for seed in seeds[3]:
    if not known_solvable(seed):
#        print("seed {} has no solve in online database".format(seed))
        hard_seeds.append(seed)
print("Found {} seeds with no solve in database, attacking each with SAT solver"
      .format(len(hard_seeds)))

for seed in hard_seeds:
    r = replay(seed)
    if not r:
        continue
    s, sol = solvable(r)
    if s:
        print("Seed {} was found to be solvable".format(seed))
#        print(sol)
    else:
        print("==============================")
        print("Found non-solvable seed {}", seed)
        print("==============================")
