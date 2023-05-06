import json
from site_api import get, api, replay
from database import Game, store, load, commit, conn
from compress import compress_deck, compress_actions, DeckCard, Action
from variants import variant_id
from hanabi import HanabiInstance, GameState, Action

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
    with conn.cursor() as cur:
        cur.execute("SELECT deck_plays, one_extra_card, one_less_card, all_or_nothing, actions FROM games WHERE id = (%s)", (game_id,))
        res = cur.fetchall()
    if len(res) == 1:
        print(res)
    else:
        print('game is completely new')
#        return

        r = get("export/{}".format(game_id))
        if r is None:
            print("Failed to export game id {}".format(game_id))
            return False, None
        assert(r['id'] == game_id)
    #    print(r)

        try:
            num_players = len(r['players'])
            seed = r['seed']
            options = r.get('options', {})
            var_id = variant_id(options['variant'])
            deck_plays = options.get('deckPlays', False)
            one_extra_card = options.get('oneExtraCard', False)
            one_less_card = options.get('oneLessCard', False)
            all_or_nothing = options.get('allOrNothing', False)
            actions = [Action.from_json(action) for action in r['actions']]
            deck = [DeckCard.from_json(card) for card in r['deck']]
        except KeyError:
            print('Error parsing JSON when exporting game {}'.format(game_id))

        # need to play through the game once to find out its score
        game = GameState(HanabiInstance(deck, num_players))
        for action in actions:
            game.make_action(action)

        try:
            compressed_deck = compress_deck(deck)
        except:
            print("Failed to compress deck while exporting game {}".format(game_id))
            raise
        try:
            compressed_actions = compress_actions(actions)
        except:
            print("Failed to compress actions while exporting game {}".format(game_id))
            raise

        with conn.cursor() as cur:
            #        cur.execute("UPDATE seeds SET deck=(%s) WHERE seed=(%s);", (deck, seed))
            cur.execute(
                    "INSERT INTO seeds (seed, num_players, variant_id, deck)"
                    "VALUES (%s, %s, %s, %s)"
                    "ON CONFLICT (seed) DO NOTHING",
                    (seed, num_players, var_id, compressed_deck)
                    )
            cur.execute(
                    "INSERT INTO games (id, num_players, score, seed, variant_id, deck_plays, one_extra_card, one_less_card, all_or_nothing, actions)"
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (game_id, num_players, game.score, seed, var_id, deck_plays, one_extra_card, one_less_card, all_or_nothing, compressed_actions))
    conn.commit()
    return True, not any([deck_plays, one_extra_card, one_less_card, all_or_nothing])

if __name__ == "__main__":
    export_game(961092)
