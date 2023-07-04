# constants.py


# some values shared by all (default) hanabi instances
HAND_SIZES = {2: 5, 3: 5, 4: 4, 5: 4, 6: 3}
NUM_STRIKES = 3
COLOR_INITIALS = 'rygbpt'
PLAYER_NAMES = ["Alice", "Bob", "Cathy", "Donald", "Emily", "Frank"]


# hanab.live stuff

# id of no variant
NO_VARIANT_ID = 0

# a map (num_suits, num_dark_suits) -> variant id of a variant on hanab.live fitting that distribution
VARIANT_IDS_STANDARD_DISTRIBUTIONS = {
        3: {
            0: 18   # 3 Suits
        },
        4: {
            0: 15   # 4 Suits
        },
        5: {
            0: 0,   # No Variant
            1: 21   # Black (5 Suits)
        },
        6: {
            0: 1,   # 6 Suits
            1: 2,   # Black (6 Suits)
            2: 60,  # Black & Gray
        }
}
