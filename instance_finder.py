import json
from site_api import get, api, replay
from sat import COLORS, solve
from database import Game, store, load, commit

def known_solvable(seed):
    link = "seed/" + seed
    r = api(link)
    rows = r['rows']
    if not rows:
        print("invalid response to seed {}".format(seed))
        return False
    for row in rows:
        if row["score"] == 25:
            return True, row["id"]
    for i in range(1, (r['total_rows'] + 99) // 100):
        page = api(link + "?page=" + str(i))
        rows = page['rows']
        for row in rows:
            if row["score"] == 25:
                return True, row["id"]
#    print("No solution found in database for seed {}".format(seed))
    return False


def solvable(replay):
    deck = replay["deck"]
    deck_str = " ".join(COLORS[c["suitIndex"]] + str(c["rank"]) for c in deck)
    return solve(deck_str, len(replay["players"]))


num_entries = 0
for i in range(0,10000):
    r = api("variants/0?page=" + str(i))
    for row in r['rows']:
        num_entries += 1
        row.pop('users')
        row.pop('datetime')
        g = Game(row)
        g.variant_id = 0
        store(g)

print('considered {} entries'.format(num_entries))
commit()
exit(0)


seeds = {2: [], 3: [], 4: [], 5: [], 6: []}
num_games = 0
for i in range(0,10000):
    r = api("variants/0?page=" + str(i))
    for row in r['rows']:
        num_games += 1
        if row['seed'] not in seeds[row['num_players']]:
            seeds[row['num_players']].append(row['seed'])
#                print('found new non-max-game in 5p: ' + row['seed'])


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
