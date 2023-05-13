import json
from typing import Dict, Optional

from site_api import get, api, replay
from database.database import Game, store, load, commit, conn, cur
from compress import compress_deck, compress_actions, DeckCard, Action, InvalidFormatError
from variants import variant_id, variant_name
from hanab_live import HanabLiveInstance, HanabLiveGameState


#
def detailed_export_game(game_id: int, score: Optional[int] = None, seed_exists: bool = False) -> None:
    """
    Downloads full details of game, inserts seed and game into DB
    If seed is already present, it is left as is
    If game is already present, game details will be updated

    :param game_id:
    :param score: If given, this will be inserted as score of the game. If not given, score is calculated
    :param seed_exists: If specified and true, assumes that the seed is already present in database.
        If this is not the case, call will raise a DB insertion error
    """

    game_json = get("export/{}".format(game_id))
    assert game_json.get('id') == game_id, "Invalid response format from hanab.live"

    players = game_json.get('players', [])
    num_players = len(players)
    seed = game_json.get('seed', None)
    options = game_json.get('options', {})
    var_id = variant_id(options.get('variant', 'No Variant'))
    deck_plays = options.get('deckPlays', False)
    one_extra_card = options.get('oneExtraCard', False)
    one_less_card = options.get('oneLessCard', False)
    all_or_nothing = options.get('allOrNothing', False)
    actions = [Action.from_json(action) for action in game_json.get('actions', [])]
    deck = [DeckCard.from_json(card) for card in game_json.get('deck', None)]

    assert (players != [])
    assert (seed is not None)

    if score is None:
        # need to play through the game once to find out its score
        game = HanabLiveGameState(HanabLiveInstance(deck, num_players, var_id))
        for action in actions:
            game.make_action(action)
        score = game.score

    try:
        compressed_deck = compress_deck(deck)
    except InvalidFormatError:
        print("Failed to compress deck while exporting game {}: {}".format(game_id, deck))
        raise
    try:
        compressed_actions = compress_actions(actions)
    except InvalidFormatError:
        print("Failed to compress actions while exporting game {}".format(game_id))
        raise

    if not seed_exists:
        cur.execute(
            "INSERT INTO seeds (seed, num_players, variant_id, deck)"
            "VALUES (%s, %s, %s, %s)"
            "ON CONFLICT (seed) DO NOTHING",
            (seed, num_players, var_id, compressed_deck)
        )

    cur.execute(
        "INSERT INTO games ("
        "id, num_players, score, seed, variant_id, deck_plays, one_extra_card, one_less_card,"
        "all_or_nothing, actions"
        ")"
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        "ON CONFLICT (id) DO UPDATE SET ("
        "deck_plays, one_extra_card, one_less_card, all_or_nothing, actions"
        ") = ("
        "EXCLUDED.deck_plays, EXCLUDED.one_extra_card, EXCLUDED.one_less_card, EXCLUDED.all_or_nothing,"
        "EXCLUDED.actions"
        ")",
        (
            game_id, num_players, score, seed, var_id, deck_plays, one_extra_card, one_less_card,
            all_or_nothing, compressed_actions
        )
    )


def process_game_row(game: Dict, var_id):
    game_id = game.get('id', None)
    seed = game.get('seed', None)
    num_players = game.get('num_players', None)
    score = game.get('score', None)

    if any(v is None for v in [game_id, seed, num_players, score]):
        raise ValueError("Unknown response format on hanab.live")

    cur.execute("SELECT seed FROM seeds WHERE seed = %s", (seed,))
    seed_exists = cur.fetchone()
    if seed_exists is not None:
        cur.execute(
            "INSERT INTO games (id, seed, num_players, score, variant_id)"
            "VALUES"
            "(%s, %s ,%s ,%s ,%s)"
            "ON CONFLICT (id) DO NOTHING",
            (game_id, seed, num_players, score, var_id)
        )
    else:
        detailed_export_game(game_id, score)


def download_games(var_id):
    name = variant_name(var_id)
    page_size = 100
    if name is None:
        raise ValueError("{} is not a known variant_id.".format(var_id))

    url = "variants/{}".format(var_id)
    r = api(url)
    if not r:
        raise RuntimeError("Failed to download request from hanab.live")

    num_entries = r.get('total_rows', None)
    if num_entries is None:
        raise ValueError("Unknown response format on hanab.live")

    cur.execute(
        "SELECT COUNT(*) FROM games WHERE variant_id = %s AND id <= "
        "(SELECT COALESCE (last_game_id, 0) FROM variant_game_downloads WHERE variant_id = %s)",
        (var_id, var_id)
    )
    num_already_downloaded_games = cur.fetchone()[0]
    next_page = num_already_downloaded_games // page_size
    last_page = (num_entries - 1) // page_size

    if num_already_downloaded_games == num_entries:
        print("Already downloaded all games for variant {} [{}]".format(var_id, name))
        return

    print(
        "Downloading remaining {} (total {}) entries for variant {} [{}]".format(
            num_entries - num_already_downloaded_games, num_entries, var_id, name
        )
    )

    for page in range(next_page, last_page + 1):
        r = api(url + "?col[0]=0&page={}".format(page))
        rows = r.get('rows', [])
        assert page == last_page or len(rows) == page_size, \
            "Received unexpected row count ({}) when querying page {}".format(len(rows), page)
        for row in rows:
            process_game_row(row, var_id)
        cur.execute(
            "INSERT INTO variant_game_downloads (variant_id, last_game_id) VALUES"
            "(%s, %s)"
            "ON CONFLICT (variant_id) DO UPDATE SET last_game_id = EXCLUDED.last_game_id",
            (var_id, r['rows'][-1]['id'])
        )
        conn.commit()
        print('Downloaded and processed page {}'.format(page))
