import json
import psycopg2
from typing import Optional, Dict

## global connection
conn = psycopg2.connect("dbname=hanab-live user=postgres")

## cursor
cur = conn.cursor()

# cur.execute("DROP TABLE games;")
# conn.commit()
# exit(0)

## check if table exists, else create it

def create_games_table():
    tablename = "games"
    cur.execute(
        "SELECT EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = '{}');".format(tablename))
    a = cur.fetchone()

    if a[0] is False:
        print("Creating table '{}'".format(tablename))
        cur.execute(
            "CREATE TABLE {} ("
            "id             INT      PRIMARY KEY,"
            "num_players    SMALLINT NOT NULL,"
            "score          SMALLINT NOT NULL,"
            "seed           TEXT     NOT NULL,"
            "variant_id     SMALLINT NOT NULL,"
            "deck_plays     BOOLEAN,"
            "one_extra_card BOOLEAN,"
            "one_less_card  BOOLEAN,"
            "all_or_nothing BOOLEAN,"
            "num_turns      SMALLINT,"
            "actions        TEXT"
            ")".format(tablename))
        conn.commit()


#    else:
#    print("table already exists")

def create_seeds_table():
    tablename = 'seeds'
    cur.execute(
        "SELECT EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = '{}');".format(tablename))
    a = cur.fetchone()

    if a[0] is False:
        print("Creating table '{}'".format(tablename))
        cur.execute(
            "CREATE TABLE {} ("
            "seed                    TEXT NOT NULL PRIMARY KEY,"
            "num_players             SMALLINT NOT NULL,"
            "variant_id              SMALLINT NOT NULL,"
            "feasible                BOOLEAN,"  # theoretical solvability
            "max_score_theoretical   SMALLINT,"  # if infeasible, max score
            "deck                    VARCHAR(60)"
            ")".format(tablename))
        conn.commit()


def create_static_tables():
    cur.execute("DROP TABLE IF EXISTS suits CASCADE;")
    cur.execute(
        "CREATE TABLE suits ("
        "id                SERIAL PRIMARY KEY,"
        "name              TEXT     NOT NULL UNIQUE,"
        "display_name      TEXT     NOT NULL,"
        "abbreviation      CHAR(1)  NOT NULL,"
        "ranks             SMALLINT NOT NULL,"  # 0: not touched by rank,  1: touched by actual rank,   2: touched by all ranks
        "colors            SMALLINT NOT NULL,"  # 0: not touched by color, 1: touched by native colors, 2: touched by all colors
        "prism             BOOLEAN  NOT NULL,"
        "dark              BOOLEAN  NOT NULL,"
        "reversed          BOOLEAN  NOT NULL"
        ")"
    )
    cur.execute(
        "CREATE INDEX suits_name_idx ON suits (name)"
    )

    cur.execute("DROP TABLE IF EXISTS colors CASCADE;")
    cur.execute(
        "CREATE TABLE colors ("
        "id       SERIAL PRIMARY KEY,"
        "name     TEXT NOT NULL UNIQUE"
        ")"
    )
    cur.execute(
        "CREATE INDEX colors_name_idx ON colors (name)"
    )

    cur.execute("DROP TABLE IF EXISTS suit_colors CASCADE;")
    cur.execute(
        "CREATE TABLE suit_colors ("
        "suit_id  INTEGER NOT NULL,"
        "color_id INTEGER NOT NULL,"
        "FOREIGN KEY (suit_id)  REFERENCES suits  (id) ON DELETE CASCADE,"
        "FOREIGN KEY (color_id) REFERENCES colors (id) ON DELETE CASCADE,"
        "UNIQUE (suit_id, color_id)"
        ")"
    )

    cur.execute("DROP TABLE IF EXISTS variants CASCADE")
    cur.execute(
        "CREATE TABLE variants ("
        "id                  SERIAL PRIMARY KEY,"
        "name                TEXT     NOT NULL UNIQUE,"
        "clue_starved        BOOLEAN  NOT NULL,"
        "throw_it_in_a_hole  BOOLEAN  NOT NULL,"
        "alternating_clues   BOOLEAN  NOT NULL,"
        "synesthesia         BOOLEAN  NOT NULL,"
        "chimneys            BOOLEAN  NOT NULL,"
        "funnels             BOOLEAN  NOT NULL,"
        "no_colors           BOOLEAN  NOT NULL,"
        "no_ranks            BOOLEAN  NOT NULL,"
        "odds_and_evens      BOOLEAN  NOT NULL,"
        "up_or_down          BOOLEAN  NOT NULL,"
        "critical_fours      BOOLEAN  NOT NULL,"
        "num_suits           SMALLINT NOT NULL,"
        "special_rank_ranks  SMALLINT NOT NULL,"
        "special_rank_colors SMALLINT NOT NULL,"
        "special_rank        SMALLINT"
        ")"
    )
    cur.execute(
        "CREATE INDEX variants_name_idx ON variants (name)"
    )

    cur.execute("DROP TABLE IF EXISTS variant_suits CASCADE")
    cur.execute(
        "CREATE TABLE variant_suits ("
        "variant_id   INT NOT NULL,"
        "suit_id      INT NOT NULL,"
        "index        SMALLINT NOT NULL,"
        "FOREIGN KEY (variant_id) REFERENCES variants (id) ON DELETE CASCADE,"
        "FOREIGN KEY (suit_id)    REFERENCES suits    (id) ON DELETE CASCADE,"
        "UNIQUE (variant_id, suit_id),"
        "UNIQUE (variant_id, index)"
        ")"
    )
    conn.commit()


def init_static_tables():
    # check if table already exists

    create = False
    tables = ['suits', 'colors', 'suit_colors', 'variants', 'variant_suits']
    for table in tables:
        cur.execute(
            "SELECT EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = '{}');".format(table)
        )
        a = cur.fetchone()
        if a[0] is False:
            create = True

    if not create:
        return

    create_static_tables()

    with open("suits.json", "r") as f:
        suits: Dict = json.loads(f.read())

    with open('variants.json', 'r') as f:
        variants = json.loads(f.read())

    suits_to_reverse = set()
    for var in variants:
        for suit in var['suits']:
            if 'Reversed' in suit:
                suits_to_reverse.add(suit.replace(' Reversed', ''))

    for suit in suits:
        name: str = suit['name']
        display_name: str = suit.get('displayName', name)
        abbreviation = suit.get('abbreviation', name[0].upper())

        all_colors = suit.get('allClueColors', False)
        no_colors = suit.get('noClueColors', False)
        all_ranks = suit.get('allClueRanks', False)
        no_ranks = suit.get('noClueRanks', False)
        prism = suit.get('prism', False)
        dark = suit.get('oneOfEach', False)

        assert([all_colors, no_colors, prism].count(True) <= 1)
        assert(not all([no_ranks, all_ranks]))

        colors = 2 if all_colors else (0 if no_colors else 1)
        ranks = 2 if all_ranks else (0 if no_ranks else 1)

        clue_colors = suit.get('clueColors', [name] if (colors == 1 and not prism) else [])

        for rev in [False, True]:
            if rev is True and name not in suits_to_reverse:
                break
            suit_name = name
            suit_name += ' Reversed' if rev else ''
            cur.execute(
                "INSERT INTO suits (name, display_name, abbreviation, ranks, colors, dark, reversed, prism)"
                "VALUES"
                "(%s, %s, %s, %s, %s, %s, %s, %s)",
                (suit_name, display_name, abbreviation, ranks, colors, dark, rev, prism)
            )
            cur.execute(
                "SELECT id FROM suits WHERE name = %s",
                (suit_name,)
            )
            suit_id = cur.fetchone()

            for color in clue_colors:
                if not rev:
                    cur.execute(
                        "INSERT INTO colors (name) VALUES (%s)"
                        "ON CONFLICT (name) DO NOTHING",
                        (color,)
                    )
                cur.execute(
                    "SELECT id FROM colors WHERE name = %s",
                    (color,)
                )
                color_id = cur.fetchone()

                cur.execute(
                    "INSERT INTO suit_colors (suit_id, color_id) VALUES"
                    "(%s, %s)",
                    (suit_id, color_id)
                )

    for var in variants:
        var_id = var['id']
        name = var['name']
        clue_starved = var.get('clueStarved', False)
        throw_it_in_a_hole = var.get('throwItInHole', False)
        alternating_clues = var.get('alternatingClues', False)
        synesthesia = var.get('synesthesia', False)
        chimneys = var.get('chimneys', False)
        funnels = var.get('funnels', False)
        no_colors = var.get('colorCluesTouchNothing', False)
        no_ranks = var.get('rankCluesTouchNothing', False)
        odds_and_evens = var.get('oddsAndEvens', False)
        up_or_down = var.get('upOrDown', False)
        critical_fours = var.get('criticalFours', False)
        suits = var['suits']
        num_suits = len(suits)
        special_rank_no_ranks = var.get('specialNoClueRanks', False)
        special_rank_all_ranks = var.get('specialAllClueRanks', False)
        special_rank_no_colors = var.get('specialNoClueColors', False)
        special_rank_all_colors = var.get('specialAllClueColors', False)
        special_rank = var.get('specialRank', None)
        clue_ranks = var.get('clueRanks', [1, 2, 3, 4, 5])

        assert(not all([special_rank_all_ranks, special_rank_no_ranks]))
        assert(not all([special_rank_all_colors, special_rank_no_colors]))

        special_rank_ranks = 2 if special_rank_all_ranks else (0 if special_rank_no_ranks else 1)
        special_rank_colors = 2 if special_rank_all_colors else (0 if special_rank_no_colors else 1)

        cur.execute(
            "INSERT INTO variants ("
            "id, name, clue_starved, throw_it_in_a_hole, alternating_clues, synesthesia, chimneys, funnels, no_colors,"
            "no_ranks, odds_and_evens, up_or_down, critical_fours, num_suits, special_rank_ranks, special_rank_colors,"
            "special_rank"
            ")"
            "VALUES"
            "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                var_id, name, clue_starved, throw_it_in_a_hole, alternating_clues, synesthesia, chimneys, funnels,
                no_colors, no_ranks, odds_and_evens, up_or_down, critical_fours, num_suits, special_rank_ranks,
                special_rank_colors, special_rank
            )
        )

        for index, suit in enumerate(suits):
            cur.execute(
                "SELECT id FROM suits WHERE name = %s",
                (suit,)
            )
            suit_id = cur.fetchone()
            if suit_id is None:
                print(suit)

            cur.execute(
                "INSERT INTO variant_suits (variant_id, suit_id, index) VALUES (%s, %s, %s)",
                (var_id, suit_id, index)
            )

    conn.commit()


create_games_table()
create_seeds_table()
init_static_tables()


class Game():
    def __init__(self, info=None):
        self.id = -1
        self.num_players = -1
        self.score = -1
        self.seed = ""
        self.variant_id = -1
        self.deck_plays = None
        self.one_extra_card = None
        self.one_less_card = None
        self.all_or_nothing = None
        self.num_turns = None
        if type(info) == dict:
            self.__dict__.update(info)

    @staticmethod
    def from_tuple(t):
        g = Game()
        g.id = t[0]
        g.num_players = t[1]
        g.score = t[2]
        g.seed = t[3]
        g.variant_id = t[4]
        g.deck_plays = t[5]
        g.one_extra_card = t[6]
        g.one_less_card = t[7]
        g.all_or_nothing = t[8]
        g.num_turns = t[9]
        return g

    def __eq__(self, other):
        return self.__dict__ == other.__dict__


def load(game_id: int) -> Optional[Game]:
    cur.execute("SELECT * from games WHERE id = {};".format(game_id))
    a = cur.fetchone()
    if a is None:
        return None
    else:
        return Game.from_tuple(a)


def store(game: Game):
    stored = load(game.id)
    if stored is None:
        #        print("inserting game with id {} into DB".format(game.id))
        cur.execute(
            "INSERT INTO games"
            "(id, num_players, score, seed, variant_id)"
            "VALUES"
            "(%s, %s, %s, %s, %s);",
            (game.id, game.num_players, game.score, game.seed, game.variant_id)
        )
    else:
        if not stored == game:
            print("Already stored game with id {}, aborting".format(game.id))
            print("Stored game is: {}".format(stored.__dict__))
            print("New game is:    {}".format(game.__dict__))


def commit():
    conn.commit()
