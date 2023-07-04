from typing import Optional
import psycopg2

# global connection
conn = psycopg2.connect("dbname=hanab-live-2 user=postgres")

# cursor
cur = conn.cursor()


# init_database_tables()
# populate_static_tables()


class Game:
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
        print("Inserted game with id {}".format(game.id))
    else:
        pass
#        if not stored == game:
#            print("Already stored game with id {}, aborting".format(game.id))
#            print("Stored game is: {}".format(stored.__dict__))
#            print("New game is:    {}".format(game.__dict__))


def commit():
    conn.commit()
