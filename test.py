import json

from variants import Variant
from variants import Suit, variant_name
from site_api import *
from download_data import download_games

from database.init_database import init_database_tables, populate_static_tables


def test_suits():
    suit = Suit.from_db(55)
    print(suit.__dict__)


def test_variant():
    var = Variant.from_db(926)
    print(var.__dict__)


if __name__ == "__main__":
    download_games(156)
    print(variant_name(17888))
    for page in range(0, 4):
        r = api("variants/0?size=20&col[0]=0&page={}".format(page))
        ids = []
        for game in r['rows']:
            ids.append(game['id'])
        r['rows'] = None
        print(json.dumps(r, indent=2))
        print(ids)
