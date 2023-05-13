/* Database schema for the tables storing information on available hanab.live variants, suits and colors */

/* Available suits. The associated id is arbitrary upon initial generation, but fixed for referentiability */
DROP TABLE IF EXISTS suits CASCADE;
CREATE TABLE suits (
    id                SERIAL PRIMARY KEY,
    name              TEXT     NOT NULL UNIQUE,
    display_name      TEXT     NOT NULL,
    abbreviation      CHAR(1)  NOT NULL,
    /**
      This is encodes how cards of this suit behave under rank clues, we use:
      0: not touched by rank,
      1: touched by actual rank of the cards
      2: touched by all ranks
    */
    rank_clues        SMALLINT NOT NULL DEFAULT 1,
    /**
      This encodes how cards of this suit behave under color clues, we use:
      0: not touched by color,
      1: touched by native colors,
      2: touched by all colors
    */
    color_clues       SMALLINT NOT NULL DEFAULT 1,
    prism             BOOLEAN  NOT NULL DEFAULT FALSE,
    dark              BOOLEAN  NOT NULL DEFAULT FALSE,
    reversed          BOOLEAN  NOT NULL DEFAULT FALSE
);
CREATE INDEX suits_name_idx ON suits (name);

/* Available color clues. The indexing is arbitrary upon initial generation, but fixed for referentiability */
DROP TABLE IF EXISTS colors CASCADE;
CREATE TABLE colors (
    id       SERIAL PRIMARY KEY,
    name     TEXT NOT NULL UNIQUE
);
CREATE INDEX colors_name_idx ON colors (name);

/**
  Stores the native colors of each suit,
  i.e. the colors that are available in a variant where that suit is available
  and which touch the suit
 */
DROP TABLE IF EXISTS suit_colors CASCADE;
CREATE TABLE suit_colors (
    suit_id  INTEGER NOT NULL,
    color_id INTEGER NOT NULL,
    FOREIGN KEY (suit_id)  REFERENCES suits  (id) ON DELETE CASCADE,
    FOREIGN KEY (color_id) REFERENCES colors (id) ON DELETE CASCADE,
    UNIQUE (suit_id, color_id)
);

/* Available variants. ids correspond to the same ids used by hanab.live */
DROP TABLE IF EXISTS variants CASCADE;
CREATE TABLE variants (
    id                  SERIAL PRIMARY KEY,
    name                TEXT     NOT NULL UNIQUE,
    clue_starved        BOOLEAN  NOT NULL DEFAULT FALSE,
    throw_it_in_a_hole  BOOLEAN  NOT NULL DEFAULT FALSE,
    /**
      If set to true, the clue types (color, rank) have to be alternating during the game.
      The type of the starting clue can still be freely chosen
      Mutually exclusive with no_color_clues and no_rank_clues
     */
    alternating_clues   BOOLEAN  NOT NULL DEFAULT FALSE,
    /**
      If set to true, no rank clues can be given
      Instead, any color given is interpreted as a simultaneous rank clue at the same time,
      where the colors correspond in order to the available ranks, wrapping around if necessary.
      To be precise,
      if (r_1, r_2, ..., r_k)  are the available rank clues in the variant
      and (c_1, c_2, ..., c_l) are the available color clues in the variant,
      then color clue c_i will be interpreted simultaneously as all rank clues r_j with i == j (mod l).
      Note that this means that if there are more colors clues than rank clues,
      some color clues are not hybrid rank clues, and conversely, if there are less color clues than rank clues,
      then some colors will be interpreted as multiple rank clues at the same time.
      Mutually exclusive with no_color_clues
     */
    synesthesia         BOOLEAN  NOT NULL DEFAULT FALSE,
    chimneys            BOOLEAN  NOT NULL DEFAULT FALSE,
    funnels             BOOLEAN  NOT NULL DEFAULT FALSE,
    no_color_clues      BOOLEAN  NOT NULL DEFAULT FALSE,
    no_rank_clues       BOOLEAN  NOT NULL DEFAULT FALSE,
    empty_color_clues   BOOLEAN  NOT NULL DEFAULT FALSE,
    empty_rank_clues    BOOLEAN  NOT NULL DEFAULT FALSE,
    odds_and_evens      BOOLEAN  NOT NULL DEFAULT FALSE,
    up_or_down          BOOLEAN  NOT NULL DEFAULT FALSE,
    critical_fours      BOOLEAN  NOT NULL DEFAULT FALSE,
    num_suits           SMALLINT NOT NULL,
    /**
      A variant can have a special rank.
      Cards of that rank will behave different from their actual suit,
      the next two parameters control this behaviour
      If set to null, there is no such special rank
     */
    special_rank        SMALLINT DEFAULT NULL,
    /**
      Encodes how cards of the special rank (if present) are touched by ranks,
      in the same manner how we encoded in @table suits
     */
    special_rank_ranks  SMALLINT NOT NULL DEFAULT 1,
    /**
      Encodes how cards of the special rank (if present) are touched by colorss,
      in the same manner how we encoded in @table suits
     */
    special_rank_colors SMALLINT NOT NULL DEFAULT 1,
    /**
      If set to true, then cards of the special rank
      will appear as different ranks depending on their suit:
      The rank values touching the deceptive special rank are chosen consecutively (starting from smallest)
      among all available ranks in the order of the suits of the variant, wrapping around if necessary.
      If set, special_rank_ranks has to be set to 1
     */
    special_deceptive   BOOLEAN NOT NULL DEFAULT FALSE,
    CHECK (special_rank_ranks = 1  OR special_deceptive IS FALSE),
    CHECK (funnels        IS FALSE OR chimneys          IS FALSE),
    CHECK (funnels        IS FALSE OR odds_and_evens    IS FALSE),
    CHECK (chimneys       IS FALSE OR odds_and_evens    IS FALSE),
    CHECK (no_rank_clues  IS FALSE OR empty_rank_clues  IS FALSE),
    CHECK (no_color_clues IS FALSE OR empty_color_clues IS FALSE),
    CHECK (no_color_clues IS FALSE OR no_rank_clues     IS FALSE),
    CHECK (no_rank_clues  IS FALSE OR alternating_clues IS FALSE),
    CHECK (no_color_clues IS FALSE OR alternating_clues IS FALSE),
    CHECK (no_color_clues IS FALSE OR synesthesia       IS FALSE)
);
CREATE INDEX variants_name_idx ON variants (name);

/**
  Stores the suits appearing in each variant
  Among all entries with fixed (variant_id, suit_id),
  the stored index controls the order of the suits appearing in this variant (in ascending order)
 */
DROP TABLE IF EXISTS variant_suits CASCADE;
CREATE TABLE variant_suits (
    variant_id   INT NOT NULL,
    suit_id      INT NOT NULL,
    index        SMALLINT NOT NULL,
    FOREIGN KEY (variant_id) REFERENCES variants (id) ON DELETE CASCADE,
    FOREIGN KEY (suit_id)    REFERENCES suits    (id) ON DELETE CASCADE,
    UNIQUE (variant_id, suit_id),
    UNIQUE (variant_id, index)
);
CREATE INDEX variant_suits_index ON variant_suits (variant_id, index);