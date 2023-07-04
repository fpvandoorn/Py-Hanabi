import alive_progress
from typing import Dict, Optional

import psycopg2.errors

from hanabi.live.site_api import get, api
from hanabi.database.database import conn, cur
from hanabi.live.compress import compress_deck, compress_actions, DeckCard, Action, InvalidFormatError
from hanabi.live.variants import variant_id, variant_name
from hanab_live import HanabLiveInstance, HanabLiveGameState

from hanabi.log_setup import logger


#
def detailed_export_game(game_id: int, score: Optional[int] = None, var_id: Optional[int] = None,
                         seed_exists: bool = False) -> None:
    """
    Downloads full details of game, inserts seed and game into DB
    If seed is already present, it is left as is
    If game is already present, game details will be updated

    :param game_id:
    :param score: If given, this will be inserted as score of the game. If not given, score is calculated
    :param var_id If given, this will be inserted as variant id of the game. If not given, this is looked up
    :param seed_exists: If specified and true, assumes that the seed is already present in database.
        If this is not the case, call will raise a DB insertion error
    """
    logger.debug("Importing game {}".format(game_id))

    assert_msg = "Invalid response format from hanab.live while exporting game id {}".format(game_id)

    game_json = get("export/{}".format(game_id))
    assert game_json.get('id') == game_id, assert_msg

    players = game_json.get('players', [])
    num_players = len(players)
    seed = game_json.get('seed', None)
    options = game_json.get('options', {})
    var_id = var_id or variant_id(options.get('variant', 'No Variant'))
    deck_plays = options.get('deckPlays', False)
    one_extra_card = options.get('oneExtraCard', False)
    one_less_card = options.get('oneLessCard', False)
    all_or_nothing = options.get('allOrNothing', False)
    starting_player = options.get('startingPlayer', 0)
    actions = [Action.from_json(action) for action in game_json.get('actions', [])]
    deck = [DeckCard.from_json(card) for card in game_json.get('deck', None)]

    assert players != [], assert_msg
    assert seed is not None, assert_msg

    if score is None:
        # need to play through the game once to find out its score
        game = HanabLiveGameState(
            HanabLiveInstance(
                deck, num_players, var_id,
                deck_plays=deck_plays,
                one_less_card=one_less_card,
                one_extra_card=one_extra_card,
                all_or_nothing=all_or_nothing
            ),
            starting_player
        )
        print(game.instance.hand_size, game.instance.num_players)
        for action in actions:
            game.make_action(action)
        score = game.score

    try:
        compressed_deck = compress_deck(deck)
    except InvalidFormatError:
        logger.error("Failed to compress deck while exporting game {}: {}".format(game_id, deck))
        raise
    try:
        compressed_actions = compress_actions(actions)
    except InvalidFormatError:
        logger.error("Failed to compress actions while exporting game {}".format(game_id))
        raise

    if not seed_exists:
        cur.execute(
            "INSERT INTO seeds (seed, num_players, variant_id, deck)"
            "VALUES (%s, %s, %s, %s)"
            "ON CONFLICT (seed) DO NOTHING",
            (seed, num_players, var_id, compressed_deck)
        )
        logger.debug("New seed {} imported.".format(seed))

    cur.execute(
        "INSERT INTO games ("
        "id, num_players, starting_player, score, seed, variant_id, deck_plays, one_extra_card, one_less_card,"
        "all_or_nothing, actions"
        ")"
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        "ON CONFLICT (id) DO UPDATE SET ("
        "deck_plays, one_extra_card, one_less_card, all_or_nothing, actions"
        ") = ("
        "EXCLUDED.deck_plays, EXCLUDED.one_extra_card, EXCLUDED.one_less_card, EXCLUDED.all_or_nothing,"
        "EXCLUDED.actions"
        ")",
        (
            game_id, num_players, starting_player, score, seed, var_id, deck_plays, one_extra_card, one_less_card,
            all_or_nothing, compressed_actions
        )
    )
    logger.debug("Imported game {}".format(game_id))


def process_game_row(game: Dict, var_id):
    game_id = game.get('id', None)
    seed = game.get('seed', None)
    num_players = game.get('num_players', None)
    score = game.get('score', None)

    if any(v is None for v in [game_id, seed, num_players, score]):
        raise ValueError("Unknown response format on hanab.live")

    cur.execute("SAVEPOINT seed_insert")
    try:
        cur.execute(
            "INSERT INTO games (id, seed, num_players, score, variant_id)"
            "VALUES"
            "(%s, %s ,%s ,%s ,%s)"
            "ON CONFLICT (id) DO NOTHING",
            (game_id, seed, num_players, score, var_id)
        )
    except psycopg2.errors.ForeignKeyViolation:
        cur.execute("ROLLBACK TO seed_insert")
        detailed_export_game(game_id, score, var_id)
    cur.execute("RELEASE seed_insert")
    logger.debug("Imported game {}".format(game_id))


def download_games(var_id):
    name = variant_name(var_id)
    page_size = 100
    if name is None:
        raise ValueError("{} is not a known variant_id.".format(var_id))

    url = "variants/{}".format(var_id)
    r = api(url, refresh=True)
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
    assert num_already_downloaded_games <= num_entries, "Database inconsistent, too many games present."
    next_page = num_already_downloaded_games // page_size
    last_page = (num_entries - 1) // page_size

    if num_already_downloaded_games == num_entries:
        logger.info("Already downloaded all games ({} many) for variant {} [{}]".format(num_entries, var_id, name))
        return
    logger.info(
        "Downloading remaining {} (total {}) entries for variant {} [{}]".format(
            num_entries - num_already_downloaded_games, num_entries, var_id, name
        )
    )

    with alive_progress.alive_bar(
            total=num_entries - num_already_downloaded_games,
            title='Downloading games for variant id {} [{}]'.format(var_id, name),
            enrich_print=False
    ) as bar:
        for page in range(next_page, last_page + 1):
            r = api(url + "?col[0]=0&page={}".format(page), refresh=page == last_page)
            rows = r.get('rows', [])
            if page == next_page:
                rows = rows[num_already_downloaded_games % 100:]
            if not (page == last_page or len(rows) == page_size):
                logger.warn('WARN: received unexpected row count ({}) on page {}'.format(len(rows), page))
            for row in rows:
                process_game_row(row, var_id)
                bar()
            cur.execute(
                "INSERT INTO variant_game_downloads (variant_id, last_game_id) VALUES"
                "(%s, %s)"
                "ON CONFLICT (variant_id) DO UPDATE SET last_game_id = EXCLUDED.last_game_id",
                (var_id, r['rows'][-1]['id'])
            )
            conn.commit()

