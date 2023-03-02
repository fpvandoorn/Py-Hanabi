import psycopg2

## global connection
conn = psycopg2.connect("dbname=hanab-live user=postgres")

## cursor
cur = conn.cursor()

## check if table exists, else create it
cur.execute("SELECT EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'games');")
a = cur.fetchone()

if a[0] is False:
    print("creating table")
    cur.execute(
            "CREATE TABLE games ("
                "id             SERIAL PRIMARY KEY,"
                "num_players    SMALLINT NOT NULL,"
                "seed           TEXT     NOT NULL,"
                "score          SMALLINT NOT NULL,"
                "variant_id     SMALLINT NOT NULL,"
                "deck_plays     BOOLEAN,"
                "one_extra_card BOOLEAN,"
                "one_less_card  BOOLEAN,"
                "all_or_nothing BOOLEAN,"
                "num_turns      SMALLINT"
            ");")
    conn.commit()
else:
    print("table already exists")
