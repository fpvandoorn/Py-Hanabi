from hanabi.live.variants import Variant
from hanabi.live.variants import Suit
from hanabi.live.download_data import download_games, detailed_export_game
from hanabi.database.database import conn, cur
from hanabi.database import init_database

from hanabi.hanabi_cli import hanabi_cli

def find_double_dark_games():
    cur.execute("SELECT variants.id, variants.name, count(suits.id) from variants "
                "inner join variant_suits on variants.id = variant_suits.variant_id "
                "left join suits on suits.id = variant_suits.suit_id "
                "where suits.dark = (%s) "
                "group by variants.id "
                "order by count(suits.id), variants.id",
                (True,)
                )
    cur2 = conn.cursor()
    r = []
    for (var_id, var_name, num_dark_suits) in cur.fetchall():
        if num_dark_suits == 2:
            cur2.execute("select count(*) from games where variant_id = (%s)", (var_id,))
            games = cur2.fetchone()[0]
            cur2.execute("select count(*) from seeds where variant_id = (%s)", (var_id, ))
            r.append((var_name, games, cur2.fetchone()[0]))
    l = sorted(r, key=lambda e: -e[1])
    for (name, games, seeds) in l:
        print("{}: {} games on {} seeds".format(name, games, seeds))


def test_suits():
    suit = Suit.from_db(55)
    print(suit.__dict__)


def test_variant():
    var = Variant.from_db(926)
    print(var.__dict__)


def check_missing_ids():
    #    start = 357849
    #    end = 358154
    start = 358393
    end = 358687
    #    broken_ids = [357913, 357914, 357915] # two of these are no variant
    #    not_supported_ids = [357925, 357957, 358081]
    broken_ids = [358627, 358630, 358632]
    not_supported_ids = [
    ]
    for game_id in range(start, end):
        if game_id in broken_ids or game_id in not_supported_ids:
            continue
        print(game_id)
        detailed_export_game(game_id)
        conn.commit()


def export_all_seeds():
    cur.execute(
        "SELECT id FROM variants ORDER BY ID"
    )
    var_ids = cur.fetchall()
    for var in var_ids:
        download_games(*var)


if __name__ == "__main__":
    hanabi_cli()
    #    init_database.init_database_tables()
#    init_database.populate_static_tables()
    exit(0)
    find_double_dark_games()
    exit(0)
    var_id = 964532
    export_all_seeds()
    exit(0)

#    init_database_tables()
#    populate_static_tables()
    download_games(1)
    print(variant_name(17888))
    for page in range(0, 4):
        r = api("variants/0?size=20&col[0]=0&page={}".format(page))
        ids = []
        for game in r['rows']:
            ids.append(game['id'])
        r['rows'] = None
        print(json.dumps(r, indent=2))
        print(ids)
