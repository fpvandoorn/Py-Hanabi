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

# requires seed AND game to already have an entry in database
# return: (successfully exported game, game without cheat options, null if not exported)
def export_game(game_id) -> [bool, bool]:
    r = get("export/{}".format(game_id))
    if r is None:
        print("Failed to export game id {}".format(game_id))
        return False, None
    assert(r['id'] == game_id)
    deck = compress_deck([DeckCard.from_json(card) for card in r['deck']])
    with conn.cursor() as cur:
        cur.execute("UPDATE seeds SET deck=(%s) WHERE seed=(%s);", (deck, r['seed']))
    try:
        actions = compress_actions([Action.from_json(a) for a in r['actions']], r['id'])
    except:
        print("Unknown action while exporting game id {}".format(game_id))
        raise
        return False, None
    options = r.get('options', {})
    deck_plays = options.get('deckPlays', False)
    one_extra_card = options.get('oneExtraCard', False)
    one_less_card = options.get('oneLessCard', False)
    all_or_nothing = options.get('allOrNothing', False)
    with conn.cursor() as cur:
        cur.execute(
                "UPDATE games SET "
                "deck_plays = (%s),"
                "one_extra_card = (%s),"
                "one_less_card = (%s),"
                "all_or_nothing = (%s),"
                "actions = (%s) "
                "WHERE id = (%s);",
                (deck_plays, one_extra_card, one_less_card, all_or_nothing, actions, game_id))
    conn.commit()
    return True, not any([deck_plays, one_extra_card, one_less_card, all_or_nothing])

if __name__ == "__main__":
    export_game(913436)
