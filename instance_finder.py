import json
from site_api import get, api, replay
from sat import COLORS, solve
from database import Game, store, load, commit, conn
from download_data import export_game


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

get_decks_of_seeds()
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
