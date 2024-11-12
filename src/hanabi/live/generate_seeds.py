import hanabi.live.compress
from hanabi.hanab_game import DeckCard
from hanabi import database
from hanabi.live.variants import Variant
from hanabi.database import games_db_interface
import random

from src.hanabi.solvers.sat import solve_sat


def get_deck(variant: Variant):
    deck = []
    for suit_index, suit in enumerate(variant.suits):
        if suit.dark:
            for rank in range(1, 6):
                deck.append(DeckCard(suit_index, rank))
        else:
            deck.append(DeckCard(suit_index, 1))
            if not suit.reversed:
                deck.append(DeckCard(suit_index, 1))
                deck.append(DeckCard(suit_index, 1))

            for rank in range(2,5):
                deck.append(DeckCard(suit_index, rank))
                deck.append(DeckCard(suit_index, rank))

            deck.append(DeckCard(suit_index, 5))
            if suit.reversed:
                deck.append(DeckCard(suit_index, 5))
                deck.append(DeckCard(suit_index, 5))
    return deck

def generate_deck(variant: Variant, num_players: int, seed: int, seed_class: int = 1):
    deck = get_deck(variant)
    seed = "p{}c{}s{}".format(num_players, seed_class, seed)
    random.seed(seed)
    random.shuffle(deck)
    return seed, deck

def link():
    seed = "p5v0sunblinkingly-kobe-prescriptively"

    deck = database.games_db_interface.load_deck(seed)
    database.cur.execute("SELECT id FROM certificate_games WHERE seed = %s", (seed,))
    (game_id, ) = database.cur.fetchone()
    actions = database.games_db_interface.load_actions(game_id, True)
    inst = hanabi.hanab_game.HanabiInstance(deck, 5)
    game = hanabi.hanab_game.GameState(inst)
    for action in actions:
        game.make_action(action)

    print(hanabi.live.compress.link(game))

def generate_decks_for_variant(variant_id: int, num_players: int, num_seeds: int, seed_class: int = 1):
    variant = Variant.from_db(variant_id)
    for seed_num in range(num_seeds):
        seed, deck = generate_deck(variant, num_players, seed_num, seed_class)
        database.cur.execute(
            "INSERT INTO seeds (seed, num_players, starting_player, variant_id, class, num) "
            "VALUES (%s, %s, %s, %s, %s, %s)"
            "ON CONFLICT (seed) DO NOTHING",
            (seed, num_players, 0, variant_id, seed_class, seed_num)
        )
        games_db_interface.store_deck_for_seed(seed, deck)

def main():
    database.global_db_connection_manager.read_config()
    database.global_db_connection_manager.connect()
    link()
#    generate_decks_for_variant(0, 2, 100)

if __name__ == '__main__':
    main()
