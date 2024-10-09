DROP TABLE IF EXISTS users CASCADE;
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    normalized_username TEXT NOT NULL UNIQUE
);


DROP TABLE IF EXISTS seeds CASCADE;
CREATE TABLE seeds (
    seed                    TEXT        NOT NULL PRIMARY KEY,
    num_players             SMALLINT    NOT NULL,
    variant_id              SMALLINT    NOT NULL,
    starting_player         SMALLINT    NOT NULL DEFAULT 0,
    feasible                BOOLEAN     DEFAULT NULL,
    max_score_theoretical   SMALLINT
);
CREATE INDEX seeds_variant_idx ON seeds (variant_id);


DROP TABLE IF EXISTS decks CASCADE;
CREATE TABLE decks (
    seed TEXT REFERENCES seeds (seed) ON DELETE CASCADE,
    /* Order of card in deck*/
    deck_index SMALLINT NOT NULL,
    /* Suit */
    suit_index SMALLINT NOT NULL,
    /* Rank */
    rank SMALLINT NOT NULL,
    PRIMARY KEY (seed, deck_index)
);

DROP TABLE IF EXISTS games CASCADE;
CREATE TABLE games (
    id                      INT      PRIMARY KEY,
    num_players             SMALLINT NOT NULL,

    starting_player         SMALLINT NOT NULL DEFAULT 0,

    variant_id              SMALLINT NOT NULL,

    timed                   BOOLEAN,
    time_base               INTEGER,
    time_per_turn           INTEGER,
    speedrun                BOOLEAN,
    card_cycle              BOOLEAN,
    deck_plays              BOOLEAN,
    empty_clues             BOOLEAN,
    one_extra_card          BOOLEAN,
    one_less_card           BOOLEAN,
    all_or_nothing          BOOLEAN,
    detrimental_characters  BOOLEAN,

    seed                    TEXT     NOT NULL REFERENCES seeds,
    score                   SMALLINT NOT NULL,
    num_turns               SMALLINT
);

CREATE INDEX games_seed_score_idx ON games (seed, score);
CREATE INDEX games_var_seed_idx ON games (variant_id, seed);
CREATE INDEX games_player_idx ON games (num_players);



DROP TABLE IF EXISTS game_participants CASCADE;
CREATE TABLE game_participants (
   id                    SERIAL    PRIMARY KEY,
   game_id               INTEGER   NOT NULL,
   user_id               INTEGER   NOT NULL,
   seat                  SMALLINT  NOT NULL, /* Needed for the "GetNotes()" function */
   FOREIGN KEY (game_id) REFERENCES games (id) ON DELETE CASCADE,
   FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
   CONSTRAINT game_participants_unique UNIQUE (game_id, user_id)
);


DROP FUNCTION IF EXISTS delete_game_of_deleted_participant;
CREATE FUNCTION delete_game_of_deleted_participant() RETURNS TRIGGER AS $_$
BEGIN
    DELETE FROM games WHERE games.id = OLD.game_id;
    RETURN OLD;
END $_$ LANGUAGE 'plpgsql';

CREATE TRIGGER delete_game_upon_participant_deletion
    AFTER DELETE ON game_participants
    FOR EACH ROW
EXECUTE PROCEDURE delete_game_of_deleted_participant();


DROP TABLE IF EXISTS game_participant_notes CASCADE;
CREATE TABLE game_participant_notes (
    game_participant_id  INTEGER   NOT NULL,
    card_order           SMALLINT  NOT NULL, /* "order" is a reserved word in PostgreSQL. */
    note                 TEXT      NOT NULL,
    FOREIGN KEY (game_participant_id) REFERENCES game_participants (id) ON DELETE CASCADE,
    PRIMARY KEY (game_participant_id, card_order)
);


DROP TABLE IF EXISTS game_actions CASCADE;
CREATE TABLE game_actions (
                              game_id  INTEGER   NOT NULL,
                              turn     SMALLINT  NOT NULL,

    /**
     * Corresponds to the "DatabaseGameActionType" enum.
     *
     * - 0 - play
     * - 1 - discard
     * - 2 - color clue
     * - 3 - rank clue
     * - 4 - game over
     */
                              type     SMALLINT  NOT NULL,

    /**
     * - If a play or a discard, corresponds to the order of the the card that was played/discarded.
     * - If a clue, corresponds to the index of the player that received the clue.
     * - If a game over, corresponds to the index of the player that caused the game to end or -1 if
     *   the game was terminated by the server.
     */
                              target   SMALLINT  NOT NULL,

    /**
     * - If a play or discard, then 0 (as NULL). It uses less database space and reduces code
     *   complexity to use a value of 0 for NULL than to use a SQL NULL:
     *   https://dev.mysql.com/doc/refman/8.0/en/data-size.html
     * - If a color clue, then 0 if red, 1 if yellow, etc.
     * - If a rank clue, then 1 if 1, 2 if 2, etc.
     * - If a game over, then the value corresponds to the "endCondition" values in "constants.go".
     */
                              value    SMALLINT  NOT NULL,

                              FOREIGN KEY (game_id) REFERENCES games (id) ON DELETE CASCADE,
                              PRIMARY KEY (game_id, turn)
);


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