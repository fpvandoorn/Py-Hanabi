import json
from site_api import get, api, replay
from database import Game, store, load, commit

def download_games(variant_id):
    url = "variants/{}".format(variant_id)
    r = api(url)
    if not r:
        print("Not a valid variant: {}".format(variant_id))
        return
    num_entries = r['total_rows']
    print("Downloading {} entries for variant {}".format(num_entries, variant_id))
    num_pages = (num_entries + 99) // 100
    for page in range(0, num_pages):
        print("Downloading page {} of {}".format(page + 1, num_pages), end = '\r')
        r = api(url + "?page={}".format(page))
        for row in r['rows']:
            row.pop('users')
            row.pop('datetime')
            g = Game(row)
            g.variant_id = variant_id
            store(g)
    print()
    print('Downloaded and stored {} entries for variant {}'.format(num_entries, variant_id))
    commit()


if __name__ == "__main__":
    download_games(1)
