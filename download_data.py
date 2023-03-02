import json
from site_api import get, api, replay
from database import Game, store, load, commit, conn
from compress import compress_deck, compress_actions, DeckCard, Action

with open('variants.json') as f:
    variants = json.loads(f.read())

def download_games(variant_id, name=None):
    url = "variants/{}".format(variant_id)
    r = api(url)
    if not r:
        print("Not a valid variant: {}".format(variant_id))
        return
    num_entries = r['total_rows']
    print("Downloading {} entries for variant {} ({})".format(num_entries, variant_id, name))
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
    print('Downloaded and stored {} entries for variant {} ({})'.format(num_entries, variant_id, name))
    commit()

def export_game(game_id) -> bool:
    r = get("export/{}".format(game_id))
    if r is None:
        print("Failed to export game id {}".format(game_id))
        return False
    assert(r['id'] == game_id)
    deck = compress_deck([DeckCard.from_json(card) for card in r['deck']])
    with conn.cursor() as cur:
        cur.execute("UPDATE seeds SET deck=(%s) WHERE seed=(%s);", (deck, r['seed']))
    try:
        actions = compress_actions([Action.from_json(a) for a in r['actions']])
    except:
        print("Unknown action while exporting game id {}".format(game_id))
        return False
    with conn.cursor() as cur:
        cur.execute("UPDATE games SET actions=(%s) WHERE id=(%s);", (actions, game_id))
    conn.commit()
    return True

if __name__ == "__main__":
    export_game(913436)
