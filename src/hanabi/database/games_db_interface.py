from typing import List, Tuple

import psycopg2.extras

import hanabi.hanab_game


def store_actions(game_id: int, actions: List[hanabi.hanab_game.Action]):
    vals = []
    for turn, action in enumerate(actions):
        vals.append((game_id, turn, action.type.value, action.target, action.value or 0))

    conn = conn_manager.get_connection()
    cur = conn.cursor()
    psycopg2.extras.execute_values(
        cur,
        "INSERT INTO game_actions (game_id, turn, type, target, value) "
        "VALUES %s "
        "ON CONFLICT (game_id, turn) "
        "DO NOTHING",
        vals
    )
    conn.commit()


def store_deck_for_seed(seed: str, deck: List[hanabi.hanab_game.DeckCard]):
    vals = []
    for index, card in enumerate(deck):
        vals.append((seed, index, card.suitIndex, card.rank))

    conn = conn_manager.get_connection()
    cur = conn.cursor()
    psycopg2.extras.execute_values(
        cur,
        "INSERT INTO seeds (seed, card_index, suit_index, rank) "
        "VALUES %s "
        "ON CONFLICT (seed, card_index) "
        "DO NOTHING",
        vals
    )
    conn.commit()


def load_actions(game_id: int) -> List[hanabi.hanab_game.Action]:
    cur = conn_manager.get_new_cursor()
    cur.execute("SELECT type, target, value FROM game_actions "
                "WHERE game_id = %s "
                "ORDER BY turn ASC",
                (game_id,))
    actions = []
    for action_type, target, value in cur.fetchall():
        actions.append(
            hanabi.hanab_game.Action(hanabi.hanab_game.ActionType(action_type), target, value)
        )
    if len(actions) == 0:
        err_msg = "Failed to load actions for game id {} from DB: No actions stored.".format(game_id)
        logger.error(err_msg)
        raise ValueError(err_msg)
    return actions


def load_deck(seed: str) -> List[hanabi.hanab_game.DeckCard]:
    cur = conn_manager.get_new_cursor()
    cur.execute("SELECT card_index, suit_index, rank FROM seeds "
                "WHERE seed = %s "
                "ORDER BY card_index ASC",
                (seed,)
                )
    deck = []
    for index, (card_index, suit_index, rank) in enumerate(cur.fetchall()):
        assert index == card_index
        deck.append(
            hanabi.hanab_game.DeckCard(suit_index, rank, card_index)
        )
    if len(deck) == 0:
        err_msg = "Failed to load deck for seed {} from DB: No cards stored.".format(seed)
        logger.error(err_msg)
        raise ValueError(err_msg)
    return deck


def load_game_parts(game_id: int) -> Tuple[hanabi.hanab_game.HanabiInstance, List[hanabi.hanab_game.Action], str]:
    """
    Loads information on game from database
    @param game_id: ID of game
    @return: Instance (i.e. deck + settings) of game, list of actions, variant name
    """
    cur = conn_manager.get_new_cursor()
    cur.execute(
        "SELECT games.num_players, games.seed, variants.clue_starved, variants.name "
        "FROM games "
        "INNER JOIN variants"
        "  ON games.variant_id = variants.id "
        "WHERE games.id = %s",
        (game_id,)
    )
    res = cur.fetchone()
    if res is None:
        err_msg = "Failed to retrieve game details of game {}.".format(game_id)
        logger.error(err_msg)
        raise ValueError(err_msg)

    # Unpack results now
    (num_players, seed, clue_starved, variant_name) = res

    actions = load_actions(game_id)
    deck = load_deck(seed)

    instance = hanabi.hanab_game.HanabiInstance(deck, num_players, clue_starved=clue_starved)
    return instance, actions, variant_name


def load_game(game_id: int) -> Tuple[hanabi.hanab_game.GameState, str]:
    instance, actions, variant_name = load_game_parts(game_id)
    game = hanabi.hanab_game.GameState(instance)
    for action in actions:
        game.make_action(action)
    return game, variant_name

