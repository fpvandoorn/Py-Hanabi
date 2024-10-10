from hanabi.hanab_game import DeckCard
from hanabi import database
from hanabi.live.variants import Variant
from hanabi.database import games_db_interface
import random

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

def generate_decks_for_variant(variant_id: int, num_players: int, num_seeds: int, seed_class: int = 1):
    variant = Variant.from_db(variant_id)
    for seed_num in range(num_seeds):
        seed, deck = generate_deck(variant, num_players, seed_num)
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
    generate_decks_for_variant(0, 2, 100)

if __name__ == '__main__':
    main()
