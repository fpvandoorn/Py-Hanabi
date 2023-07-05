import alive_progress
from typing import Dict, Optional

import psycopg2.errors

from hanabi import hanab_game
from hanabi.database import database
from hanabi.live import site_api
from hanabi.live import compress
from hanabi.live import variants
from hanabi.live import hanab_live

from hanabi import logger


class GameExportError(ValueError):
    def __init__(self, game_id, msg):
        super().__init__("When exporting game {}: {}".format(game_id, msg))

    pass


class GameExportNoResponseFromSiteError(GameExportError):
    def __init__(self, game_id):
        super().__init__(game_id, "No response from site")


class GameExportInvalidResponseTypeError(GameExportError):
    def __init__(self, game_id, response_type):
        super().__init__(game_id, "Invalid response type (expected json, got {})".format(
            response_type, game_id
        ))

    pass


class GameExportInvalidFormatError(GameExportError):
    def __init__(self, game_id, msg):
        super().__init__(game_id, "Invalid response format: {}".format(msg))


class GameExportInvalidNumberOfPlayersError(GameExportInvalidFormatError):
    def __init__(self, game_id, expected, received):
        super().__init__(
            game_id,
            "Received invalid list of players: Expected {} many, got {}".format(expected, received)
        )


#
def detailed_export_game(
          game_id: int
        , score: Optional[int] = None
        , var_id: Optional[int] = None
        , seed_exists: bool = False
) -> None:
    """
    Downloads full details of game from hanab.live, inserts seed and game into DB
    If seed is already present, it is left as is
    If game is already present, game details will be updated

    :param game_id: id of game to export
    :param score: If given, this will be inserted as score of the game. If not given, score is calculated
    :param var_id: If given, this will be inserted as variant id of the game. If not given, this is looked up
    :param seed_exists: If specified and true, assumes that the seed is already present in database.
        If this is not the case, call will raise a DB insertion error

    :raises GameExportError and its child classes
    """

    logger.debug("Importing game {}".format(game_id))

    game_json = site_api.get("export/{}".format(game_id))
    if game_json is None:
        raise GameExportNoResponseFromSiteError
    if type(game_json) != dict:
        raise GameExportInvalidResponseTypeError(game_id, type(game_json))

    if game_json.get('id', None) != game_id:
        raise GameExportInvalidFormatError(game_id, "Unexpected game_id {} received, expected {}".format(
            game_json.get('id'), game_id
        ))

    players = game_json.get('players', [])
    num_players = len(players)
    if num_players < 2:
        raise GameExportInvalidNumberOfPlayersError(game_id, "≥2", num_players)

    seed = game_json.get('seed', None)
    if type(seed) != str:
        raise GameExportInvalidFormatError(game_id, "Unexpected seed, expected string, got {}".format(seed))

    options = game_json.get('options', {})
    var_id = var_id or variants.variant_id(options.get('variant', 'No Variant'))
    deck_plays = options.get('deckPlays', False)
    one_extra_card = options.get('oneExtraCard', False)
    one_less_card = options.get('oneLessCard', False)
    all_or_nothing = options.get('allOrNothing', False)
    starting_player = options.get('startingPlayer', 0)

    try:
        actions = [hanab_game.Action.from_json(action) for action in game_json.get('actions', [])]
    except hanab_game.ParseError as e:
        raise GameExportInvalidFormatError(game_id, "Failed to parse actions") from e

    try:
        deck = [hanab_game.DeckCard.from_json(card) for card in game_json.get('deck', None)]
    except hanab_game.ParseError as e:
        raise GameExportInvalidFormatError(game_id, "Failed to parse deck") from e

    if score is None:
        # need to play through the game once to find out its score
        game = hanab_live.HanabLiveGameState(
            hanab_live.HanabLiveInstance(
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
        compressed_deck = compress.compress_deck(deck)
    except compress.InvalidFormatError as e:
        logger.error("Failed to compress deck while exporting game {}: {}".format(game_id, deck))
        raise GameExportInvalidFormatError(game_id, "Failed to compress deck") from e

    try:
        compressed_actions = compress.compress_actions(actions)
    except compress.InvalidFormatError as e:
        logger.error("Failed to compress actions while exporting game {}".format(game_id))
        raise GameExportInvalidFormatError(game_id, "Failed to compress actions") from e

    if not seed_exists:
        database.cur.execute(
            "INSERT INTO seeds (seed, num_players, variant_id, deck)"
            "VALUES (%s, %s, %s, %s)"
            "ON CONFLICT (seed) DO NOTHING",
            (seed, num_players, var_id, compressed_deck)
        )
        logger.debug("New seed {} imported.".format(seed))

    database.cur.execute(
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


def _process_game_row(game: Dict, var_id, export_all_games: bool = False):
    game_id = game.get('id', None)
    seed = game.get('seed', None)
    num_players = game.get('num_players', None)
    users = game.get('users', "").split(", ")
    score = game.get('score', None)

    if any(v is None for v in [game_id, seed, num_players, score]):
        raise ValueError("Unknown response format on hanab.live")

    if len(users) != num_players:
        raise GameExportInvalidNumberOfPlayersError(game_id, num_players, users)

    if export_all_games:
        detailed_export_game(game_id, score=score, var_id=var_id)
        logger.debug("Imported game {}".format(game_id))
        return

    database.cur.execute("SAVEPOINT seed_insert")
    try:
        database.cur.execute(
            "INSERT INTO games (id, seed, num_players, score, variant_id)"
            "VALUES"
            "(%s, %s ,%s ,%s ,%s)"
            "ON CONFLICT (id) DO NOTHING",
            (game_id, seed, num_players, score, var_id)
        )
    except psycopg2.errors.ForeignKeyViolation:
        # Sometimes, seed is not present in the database yet, then we will have to query the full game details
        # (including the seed) to export it accordingly
        database.cur.execute("ROLLBACK TO seed_insert")
        detailed_export_game(game_id, score=score, var_id=var_id)
    database.cur.execute("RELEASE seed_insert")
    logger.debug("Imported game {}".format(game_id))


def download_games(var_id, export_all_games: bool = False):
    name = variants.variant_name(var_id)
    page_size = 100
    if name is None:
        raise ValueError("{} is not a known variant_id.".format(var_id))

    url = "variants/{}".format(var_id)
    r = site_api.api(url, refresh=True)
    if not r:
        raise RuntimeError("Failed to download request from hanab.live")

    num_entries = r.get('total_rows', None)
    if num_entries is None:
        raise ValueError("Unknown response format on hanab.live")

    database.cur.execute(
        "SELECT COUNT(*) FROM games WHERE variant_id = %s AND id <= "
        "(SELECT COALESCE (last_game_id, 0) FROM variant_game_downloads WHERE variant_id = %s)",
        (var_id, var_id)
    )
    num_already_downloaded_games = database.cur.fetchone()[0]
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
            r = site_api.api(url + "?col[0]=0&page={}".format(page), refresh=page == last_page)
            rows = r.get('rows', [])
            if page == next_page:
                rows = rows[num_already_downloaded_games % 100:]
            if not (page == last_page or len(rows) == page_size):
                logger.warn('WARN: received unexpected row count ({}) on page {}'.format(len(rows), page))
            for row in rows:
                _process_game_row(row, var_id, export_all_games)
                bar()
            database.cur.execute(
                "INSERT INTO variant_game_downloads (variant_id, last_game_id) VALUES"
                "(%s, %s)"
                "ON CONFLICT (variant_id) DO UPDATE SET last_game_id = EXCLUDED.last_game_id",
                (var_id, r['rows'][-1]['id'])
            )
            database.conn.commit()
