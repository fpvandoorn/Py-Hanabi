#! /bin/python3
import collections
import sys

from enum import Enum
from typing import Optional

from hanabi import logger
from hanabi import hanab_game
from hanabi.live import compress
from hanabi import database


class CardType(Enum):
    Dispensable = -1
    Trash = 0
    Playable = 1
    Critical = 2
    DuplicateVisible = 3
    UniqueVisible = 4


class CardState:
    def __init__(self, card_type: CardType, card: hanab_game.DeckCard, weight: Optional[int] = 1):
        self.card_type = card_type
        self.card = card
        self.weight = weight

    def __repr__(self):
        match self.card_type:
            case CardType.Trash:
                return "Trash ({})".format(self.card)
            case CardType.Playable:
                return "Playable ({}) with weight {}".format(self.card, self.weight)
            case CardType.Critical:
                return "Critical ({})".format(self.card)
            case CardType.DuplicateVisible:
                return "Useful (duplicate visible) ({}) with weight {}".format(self.card, self.weight)
            case CardType.UniqueVisible:
                return "Useful (unique visible) ({}) with weight {}".format(self.card, self.weight)


# TODO
def card_type(game_state, card):
    played = game_state.stacks[card.suitIndex]
    if card.rank <= played:
        return CardType.Trash
    elif card.rank == played + 1:
        return CardType.Playable
    elif card.rank == 5 or card in game_state.trash:
        return CardType.Critical
    else:
        visible_cards = sum((game_state.hands[player] for player in range(game_state.num_players)), [])
        if visible_cards.count(card) >= 2:
            return CardType.DuplicateVisible
        else:
            return CardType.UniqueVisible


class WeightedCard:
    def __init__(self, card, weight: Optional[int] = None):
        self.card = card
        self.weight = weight

    def __repr__(self):
        return "{} with weight {}".format(self.card, self.weight)


class HandState:
    def __init__(self, player: int, game_state: hanab_game.GameState):
        self.trash = []
        self.playable = []
        self.critical = []
        self.dupes = []
        self.uniques = []
        for card in game_state.hands[player]:
            match card_type(game_state, card):
                case CardType.Trash:
                    self.trash.append(WeightedCard(card))
                case CardType.Playable:
                    if card not in map(lambda c: c.card, self.playable):
                        self.playable.append(WeightedCard(card))
                    else:
                        self.trash.append(card)
                case CardType.Critical:
                    self.critical.append(WeightedCard(card))
                case CardType.UniqueVisible:
                    self.uniques.append(WeightedCard(card))
                case CardType.DuplicateVisible:
                    copy = next((w for w in self.dupes if w.card == card), None)
                    if copy is not None:
                        self.dupes.remove(copy)
                        self.critical.append(copy)
                        self.trash.append(card)
                    else:
                        self.dupes.append(WeightedCard(card))
        self.playable.sort(key=lambda c: c.card.rank)
        self.dupes.sort(key=lambda c: c.card.rank)
        self.uniques.sort(key=lambda c: c.card.rank)
        if len(self.trash) > 0:
            self.best_discard = self.trash[0]
            self.discard_badness = 0
        elif len(self.dupes) > 0:
            self.best_discard = self.dupes[0]
            self.discard_badness = 8 - game_state.num_players
        elif len(self.uniques) > 0:
            self.best_discard = self.uniques[-1]
            self.discard_badness = 80 - 10 * self.best_discard.card.rank
        elif len(self.playable) > 0:
            self.best_discard = self.playable[-1]
            self.discard_badness = 80 - 10 * self.best_discard.card.rank
        else:
            assert len(self.critical) > 0, "Programming error."
            self.best_discard = self.critical[-1]
            self.discard_badness = 600 - 100 * self.best_discard.card.rank

    def num_useful_cards(self):
        return len(self.dupes) + len(self.uniques) + len(self.playable) + len(self.critical)


class CheatingStrategy:
    def __init__(self, game_state: hanab_game.GameState):
        self.game_state = game_state

    def make_move(self):
        hand_states = [HandState(player, self.game_state) for player in range(self.game_state.num_players)]

        modified_pace = self.game_state.pace - sum(
            1 for state in hand_states if len(state.trash) == self.game_state.hand_size
        )

        cur_hand = hand_states[self.game_state.turn]

        print([state.__dict__ for state in hand_states])
        print(self.game_state.pace)
        exit(0)


class GreedyStrategy():
    def __init__(self, game_state: hanab_game.GameState):
        self.game_state = game_state

        self.earliest_draw_times = []
        for s in range(0, game_state.instance.num_suits):
            self.earliest_draw_times.append([])
            for r in range(1, 6):
                self.earliest_draw_times[s].append(max(
                    game_state.deck.index(hanab_game.DeckCard(s, r)) - game_state.hand_size * game_state.num_players + 1,
                    0 if r == 1 else self.earliest_draw_times[s][r - 2]
                ))

        # Currently, we do not add the time the 5 gets drawn to this, since this is rather a measurument on how
        # bad a suit is in terms of having to hold on to other cards that are not playable *yet*
        self.suit_badness = [sum(self.earliest_draw_times[s][:-1]) for s in range(0, game_state.num_suits)]

    def make_move(self):
        hand_states = [[CardState(card_type(self.game_state, card), card, None) for card in self.game_state.hands[p]]
                       for p in range(self.game_state.num_players)]

        # find dupes in players hands, mark one card crit and the other one trash
        p = False
        for states in hand_states:
            counter = collections.Counter(map(lambda state: state.card, states))
            for card in counter:
                if counter[card] >= 2:
                    dupes = (cstate for cstate in states if cstate.card == card)
                    first = next(dupes)
                    if first.card_type == CardType.Dispensable:
                        first.card_type = CardType.Critical
                    for dupe in dupes:
                        dupe.card_type = CardType.Trash

        def hand_badness(states):
            if any(state.card_type == CardType.Playable for state in states):
                return 0
            crits = [state for state in states if state.card_type == CardType.Critical]
            crits_val = sum(map(lambda state: state.card.rank, crits))
            if any(state.card_type == CardType.Playable for state in states):
                return crits_val

        def player_distance(f, t):
            return ((t - f - 1) % self.game_state.num_players) + 1

        for (player, states) in enumerate(hand_states):
            for state in states:
                if state.card_type == CardType.Playable:
                    copy_holders = set(self.game_state.holding_players(state.card))
                    copy_holders.remove(player)
                    connecting_holders = set(
                        self.game_state.holding_players(hanab_game.DeckCard(state.card.suitIndex, state.card.rank + 1)))

                    if len(copy_holders) == 0:
                        # card is unique, imortancy is based lexicographically on whether somebody has the conn. card and the rank
                        state.weight = (6 if len(connecting_holders) > 0 else 1) * (6 - state.card.rank)
                    else:
                        # copy is available somewhere else
                        if len(connecting_holders) == 0:
                            # card is not urgent
                            state.weight = 0.5 * (6 - state.card.rank)
                        else:
                            # there is a copy and there is a connecting card. check if they are out of order
                            turns_to_copy = min(map(lambda holder: player_distance(player, holder), copy_holders))
                            turns_to_conn = max(map(lambda holder: player_distance(player, holder), connecting_holders))
                            if turns_to_copy < turns_to_conn:
                                # our copy is not neccessary for connecting card to be able to play
                                state.weight = 0.5 * (6 - state.card.rank)
                            else:
                                # our copy is important, scale it little less than if it were unique
                                state.weight = 4 * (6 - state.card.rank)
                elif state.card_type == CardType.Dispensable:
                    try:
                        # TODO: consider duplicate in hand
                        copy_holders = list(self.game_state.holding_players(state.card))
                        copy_holders.remove(player)
                        nextCopy = self.game_state.deck[self.game_state.progress:].index(card)
                    except:
                        nextCopy = 1
                    #                    state.weight = self.suit_badness[state.card.suitIndex] * nextCopy + 2 * (5 - state.card.rank)
                    state.weight = nextCopy + 2 * (5 - state.card.rank)

        cur_hand = hand_states[self.game_state.turn]
        plays = [cstate for cstate in cur_hand if cstate.card_type == CardType.Playable]
        trash = next((cstate for cstate in cur_hand if cstate.card_type == CardType.Trash), None)

        # actual decision on what to do

        if len(plays) > 0:
            play = max(plays, key=lambda s: s.weight)
            self.game_state.play(play.card.deck_index)
        elif self.game_state.clues == 8:
            self.game_state.clue()
        elif trash is not None:
            self.game_state.discard(trash.card.deck_index)
        elif self.game_state.clues == 0:
            dispensable = [cstate for cstate in cur_hand if cstate.card_type == CardType.Dispensable]
            if len(dispensable) == 0:
                self.game_state.in_lost_state = True
            #                raise ValueError("Lost critical card")
            else:
                discard = min(dispensable, key=lambda s: s.weight)
                self.game_state.discard(discard.card.deck_index)
        else:
            self.game_state.clue()


def run_deck(instance: hanab_game.HanabiInstance) -> hanab_game.GameState:
    gs = hanab_game.GameState(instance)
    strat = CheatingStrategy(gs)
    while not gs.is_over():
        strat.make_move()
    return gs


def run_samples(num_players, sample_size):
    logger.info("Running {} test games on {} players using greedy strategy.".format(sample_size, num_players))
    won = 0
    lost = 0
    cur = database.conn.cursor()
    cur.execute(
        "SELECT seed, num_players, deck, variant_id "
        "FROM seeds WHERE variant_id = 0 AND num_players = (%s)"
        "ORDER BY seed DESC LIMIT (%s)",
        (num_players, sample_size))
    for r in cur:
        seed, num_players, deck_str, var_id = r
        deck = compress.decompress_deck(deck_str)
        instance = hanab_game.HanabiInstance(deck, num_players)
        final_game_state = run_deck(instance)
        if final_game_state.score != instance.max_score:
            logger.verbose(
                "Greedy strategy lost {}-player seed {:10} {}:\n{}"
                .format(num_players, seed, str(deck), compress.link(final_game_state))
            )
            lost += 1
        else:
            won += 1
        print("won: {:4}, lost: {:4}".format(won, lost), end="\r")
    logger.info("Won {} ({}%) and lost {} ({}%) from sample of {} test games using greedy strategy.".format(
        won, round(100 * won / sample_size, 2), lost, round(100 * lost / sample_size, 2), sample_size
    ))
