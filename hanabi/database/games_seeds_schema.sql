DROP TABLE IF EXISTS seeds CASCADE;
CREATE TABLE seeds (
    seed                    TEXT        NOT NULL PRIMARY KEY,
    num_players             SMALLINT    NOT NULL,
    variant_id              SMALLINT    NOT NULL,
    deck                    VARCHAR(62) NOT NULL,
    starting_player         SMALLINT    NOT NULL DEFAULT 0,
    feasible                BOOLEAN     DEFAULT NULL,
    max_score_theoretical   SMALLINT
);
CREATE INDEX seeds_variant_idx ON seeds (variant_id);


DROP TABLE IF EXISTS games CASCADE;
CREATE TABLE games (
    id                      INT      PRIMARY KEY,
    seed                    TEXT     NOT NULL REFERENCES seeds,
    num_players             SMALLINT NOT NULL,
    score                   SMALLINT NOT NULL,
    variant_id              SMALLINT NOT NULL,
    deck_plays              BOOLEAN,
    one_extra_card          BOOLEAN,
    one_less_card           BOOLEAN,
    all_or_nothing          BOOLEAN,
    detrimental_characters  BOOLEAN,
    num_turns               SMALLINT,
    actions                 TEXT
);
CREATE INDEX games_seed_score_idx ON games (seed, score);
CREATE INDEX games_var_seed_idx ON games (variant_id, seed);
CREATE INDEX games_player_idx ON games (num_players);


DROP TABLE IF EXISTS score_upper_bounds;
CREATE TABLE score_upper_bounds (
    seed              TEXT     NOT NULL REFERENCES seeds ON DELETE CASCADE,
    score_upper_bound SMALLINT NOT NULL,
    reason            SMALLINT NOT NULL,
    UNIQUE (seed, reason)
);

DROP TABLE IF EXISTS score_lower_bounds;
CREATE TABLE score_lower_bounds (
  seed              TEXT NOT NULL REFERENCES seeds ON DELETE CASCADE,
  score_lower_bound SMALLINT NOT NULL,
  game_id           INT REFERENCES games ON DELETE CASCADE,
  actions           TEXT,
  CHECK (num_nonnulls(game_id, actions) = 1)
);