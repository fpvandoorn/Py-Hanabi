import json
import requests

from variants import Variant
from variants import Suit, variant_name
from site_api import *
from download_data import download_games, detailed_export_game
from check_game import check_game
from compress import link
from database.database import conn

from database.init_database import init_database_tables, populate_static_tables


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


if __name__ == "__main__":
    var_id = 964490
    check_missing_ids()
    exit(0)

#    detailed_export_game(var_id)
#    turn, state = check_game(var_id)
#    if turn != 0:
#        print("https://hanab.live/replay/{}".format(var_id))
#        print(turn, link(state))

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
