import psycopg2
from typing import Optional

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
    cur.execute("SELECT EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = '{}');".format(tablename))
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
                ");".format(tablename))
        conn.commit()
#    else:
    #    print("table already exists")

def create_seeds_table():
    tablename = 'seeds'
    cur.execute("SELECT EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = '{}');".format(tablename))
    a = cur.fetchone()

    if a[0] is False:
        print("Creating table '{}'".format(tablename))
        cur.execute(
                "CREATE TABLE {} ("
                    "seed                    TEXT NOT NULL PRIMARY KEY,"
                    "num_players             SMALLINT NOT NULL,"
                    "variant_id              SMALLINT NOT NULL,"
                    "feasible                BOOLEAN," # theoretical solvability
                    "max_score_theoretical   SMALLINT" # if infeasible, max score
                    "deck                    VARCHAR(60)"
                ");".format(tablename))
        conn.commit()

create_games_table()
create_seeds_table()



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
