from typing import List, Tuple, Optional

import psycopg2.extras

import hanabi.hanab_game
import hanabi.live.hanab_live
from hanabi import logger

from hanabi.database import conn, cur

def get_actions_table_name(cert_game: bool):
    return "certificate_game_actions" if cert_game else "game_actions"


def store_actions(game_id: int, actions: List[hanabi.hanab_game.Action], cert_game: bool = False):
    vals = []
    for turn, action in enumerate(actions):
        vals.append((game_id, turn, action.type.value, action.target, action.value or 0))

    psycopg2.extras.execute_values(
        cur,
        "INSERT INTO {} (game_id, turn, type, target, value) "
        "VALUES %s "
        "ON CONFLICT (game_id, turn) "
        "DO NOTHING".format(get_actions_table_name(cert_game)),
        vals
    )
    conn.commit()


def store_deck_for_seed(seed: str, deck: List[hanabi.hanab_game.DeckCard]):
    vals = []
    for index, card in enumerate(deck):
        vals.append((seed, index, card.suitIndex, card.rank))

    psycopg2.extras.execute_values(
        cur,
        "INSERT INTO decks (seed, deck_index, suit_index, rank) "
        "VALUES %s "
        "ON CONFLICT (seed, deck_index) DO UPDATE SET "
        "(suit_index, rank) = (excluded.suit_index, excluded.rank)",
        vals
    )
    conn.commit()


def load_actions(game_id: int, cert_game: bool = False) -> List[hanabi.hanab_game.Action]:
    cur.execute("SELECT type, target, value FROM {} "
                "WHERE game_id = %s "
                "ORDER BY turn ASC".format(get_actions_table_name(cert_game)),
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
    cur.execute("SELECT deck_index, suit_index, rank FROM decks "
                "WHERE seed = %s "
                "ORDER BY deck_index ASC",
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

def load_instance(seed: str) -> Optional[hanabi.live.hanab_live.HanabLiveInstance]:
    cur.execute(
        "SELECT num_players, variant_id "
        "FROM seeds WHERE seed = %s ",
        (seed,)
    )
    res = cur.fetchone()
    if res is None:
        return None
    (num_players, var_id) = res
    deck = load_deck(seed)
    return hanabi.live.hanab_live.HanabLiveInstance(deck, num_players, var_id)


def load_game_parts(game_id: int, cert_game: bool = False) -> Tuple[hanabi.live.hanab_live.HanabLiveInstance, List[hanabi.hanab_game.Action]]:
    """
    Loads information on game from database
    @param game_id: ID of game
    @return: Instance (i.e. deck + settings) of game, list of actions, variant name
    """
    cur.execute(
        "SELECT "
        "games.num_players, games.seed, games.one_extra_card, games.one_less_card, games.deck_plays, "
        "games.all_or_nothing,"
        "variants.clue_starved, variants.name, variants.id, variants.throw_it_in_a_hole "
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
    (num_players, seed, one_extra_card, one_less_card, deck_plays, all_or_nothing, clue_starved, variant_name, variant_id, throw_it_in_a_hole) = res

    actions = load_actions(game_id, cert_game)
    deck = load_deck(seed)

    instance = hanabi.live.hanab_live.HanabLiveInstance(
        deck=deck,
        num_players=num_players,
        variant_id=variant_id,
        one_extra_card=one_extra_card,
        one_less_card=one_less_card,
        fives_give_clue=not throw_it_in_a_hole,
        deck_plays=deck_plays,
        all_or_nothing=all_or_nothing,
        clue_starved=clue_starved
    )
    return instance, actions


def load_game(game_id: int, cert_game: bool = False) -> hanabi.live.hanab_live.HanabLiveGameState:
    instance, actions = load_game_parts(game_id, cert_game)
    game = hanabi.live.hanab_live.HanabLiveGameState(instance)
    for action in actions:
        game.make_action(action)
    return game

