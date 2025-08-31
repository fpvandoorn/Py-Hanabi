import copy
import itertools
from typing import Optional, Tuple

from pysat.formula import IDPool, CNF
from pysat.solvers import Glucose42
from pysat.card import CardEnc

from hanabi import logger
from hanabi import constants
from hanabi import hanab_game


# literals to model game as sat instance to check for feasibility
# variants 'throw it in a hole', 'clue starved' and 'up or down' currently not handled
class Literals():
    # num_suits is total number of suits, i.e. also counts the dark suits
    # default distribution among all suits is assumed
    def __init__(self, vpool : IDPool, instance: hanab_game.HanabiInstance):
        # clues_gt[m, i] == "after move m we have more than i clues", in clue starved, this counts half clues
        self.clues_gt = {
            (m, i) : vpool.id(f"m{m}clues_gt{i}")
            for i in range(-instance.clue_cost, instance.max_clues + 1)
            for m in range(-1, instance.max_winning_moves)
        }

        # strikes[m, i] == "after move m we have more than i strikes"
        self.strikes_gt = {
                (m, i) : vpool.id(f"m{m}strikes_gt{i}")
                for i in range(instance.num_strikes)
                for m in range(-1, instance.max_winning_moves)
        }

        # extraturn[m] = "turn m is a move part of the extra round or a dummy turn"
        self.extraturn = {
            m: vpool.id(f"m{m}extra")
            for m in range(instance.max_winning_moves)
        }

        # dummyturn[m] = "turn m is a dummy nurn and not actually part of the game"
        self.dummyturn = {
            m: vpool.id(f"m{m}dummy")
            for m in range(instance.max_winning_moves)
        }

        # use_le[m, i] == "we play/discard deck[i] on or before turn m"
        self.use_le = {
            (m, i) : vpool.id(f"m{m}use_le{i}")
            for i in range(instance.deck_size)
            for m in range(-1, instance.max_winning_moves)
        }

        # use[m, i] == "we play/discard deck[i] on or before turn m"
        self.use = {
            (m, i) : vpool.id(f"m{m}use{i}")
            for i in range(instance.deck_size)
            for m in range(instance.max_winning_moves)
        }

        # draw_ge[m, i] == "card i is drawn turn m or later" or equivalently "at turn (m-1), the top card of the deck is i or less"
        self.draw_ge = {
                (m, i): vpool.id(f"m{m}draw_ge{i}")
                for i in range(instance.num_dealt_cards - 1, instance.deck_size)
                for m in range(instance.max_winning_moves)
        }

        # draw[m, i] == "at move m we draw deck card i"
        self.draw = {
            (m, i): vpool.id(f"m{m}draw{i}")
            for i in range(instance.num_dealt_cards, instance.deck_size)
            for m in range(instance.max_winning_moves)
        }

        # strike[m] = "at move m we get a strike"
        self.strike = {
            m: vpool.id(f"m{m}strike")
            for m in range(instance.max_winning_moves)
        }

        # progress[m, suitIndex, rank] == "after move m we have played in suitIndex up to at least rank"
        self.progress = {
            (m, s, r): vpool.id(f"m{m}progress{s}_{r}")
            for m in range(-1, instance.max_winning_moves)
            for s in range(instance.num_suits)
            for r in range(1, 6)
        }

        ## Utility variables

        # clue[m] == "at move m we clue (or it is a dummy turn)"
        self.clue = {m: vpool.id(f"m{m}clue") for m in range(instance.max_winning_moves)}

        # draw_any[m] == "at move m we draw a card"
        self.draw_any = {m: vpool.id(f"m{m}draw_any") for m in range(instance.max_winning_moves)}

        # play[m] == "at move m we succesfully play a card"
        self.play = {m: vpool.id(f"m{m}play") for m in range(instance.max_winning_moves)}

        # play5[m] == "at move m we succesfully play a 5"
        self.play5 = {m: vpool.id(f"m{m}play5") for m in range(instance.max_winning_moves)}

        # incr_clues[m] == "at move m we obtain a clue"
        self.incr_clues = {m: vpool.id(f"m{m}add_clue") for m in range(instance.max_winning_moves)}

        ## Variables to (hopefully) improve performance

        # pace_gt[m, i] means that pace at turn m is at least i
        self.pace_gt = {
            (m, i): vpool.id(f"m{m}pace_gt{i}")
            for m in range(-1, instance.max_winning_moves)
            for i in range(-1, instance.initial_pace + 1)
        }



        # number of wasted clues up till turn m
        # self.wasted_clue = { -1: Int(0),
        #                      **{m: vpool.id(f"m{m}wasted_clue", INT) for m in range(instance.max_winning_moves + instance.num_suits)} }

def max_scores(instance: hanab_game.HanabiInstance, i : int):
    """returns the max scores achievable before card i is drawn"""
    gotten = { c : [] for c in range(instance.num_suits) }

    for j in range(i):
        gotten[instance.deck[j].suitIndex] += [instance.deck[j].rank]

    max_plays = []
    for c in range(instance.num_suits):
        notgotten = [r for r in range(1, 6) if r not in gotten[c]]
        max_plays += [5 if notgotten == [] else min(notgotten) - 1]
    return max_plays

def max_pace(instance: hanab_game.HanabiInstance, i : int) -> int:
    """returns the max pace at which card i can be drawn"""
    depth = i - instance.num_dealt_cards # 0-indexed
    return instance.initial_pace - max(0, depth + 1 - sum(max_scores(instance, i)))

# def pace_constraints(instance: hanab_game.HanabiInstance, ls : Literals, first_turn):
#     """constaints we can derive from pace considerations."""
#     return \
#         [ Implies(ls.draw[m, i], LE(ls.pace[m], Int(max_pace(instance, i))))
#                 for i in range(instance.num_dealt_cards, instance.deck_size)
#                 for m in range(first_turn, instance.max_winning_moves) ] + \
#         [ Implies(ls.draw[m, i], ls.progress[m, c, max_scores(instance, i)[c] - max_pace(instance, i)])
#                 for i in range(instance.num_dealt_cards, instance.deck_size)
#                 for c in range(instance.num_suits)
#                 for m in range(first_turn, instance.max_winning_moves)
#                 if max_scores(instance, i)[c] > max_pace(instance, i)]

def min_turn(instance: hanab_game.HanabiInstance, i : int, total_turns = None) -> int:
    """returns the first turn that card i can be drawn.
    When `turns` is not None, this is computed for a game that has at most `turns`
    fewer total turns than the maximum possible length."""
    depth = i - instance.num_dealt_cards # 0-indexed
    scores = max_scores(instance, i)
    score = sum(scores)
    possible_fiveplays = scores.count(5)
    # minimum number of 5s that have to be played
    minimum_fiveplays = max(0, possible_fiveplays - max_pace(instance, i))
    # (minimum number of) clues gotten from 5s minus number of misplays
    clues_modifier = -2 if total_turns is None else max(-2, minimum_fiveplays - total_turns)
    return depth + max(0, depth + 1 - score + clues_modifier)

def game_length_constraints(instance: hanab_game.HanabiInstance, ls : Literals, first_turn, k : int):
    """The constraints we can add to a game of exactly `maxlength - k` turns:
    at most `k + l` clues can be wasted.
    Here `l` is the minimum number of 5s that must be played in the last `#players + 1` plays (i.e. `l = 1 + n // 5`).
    A wasted clue is
    * a strike
    * a 5 played at 8 clues
    * a suit where the 5 has not been played before the final round starts.
    Possibly we could also add:
    * clues when the final round starts
    * number of non-plays in the final round (however, we should be careful to not double count this with suits where the 5 has not been played;
        in a 5p 56-turn game it is allowed that one player doesn't play in the final round.)

    For `k = 0` we use an encoding that is significantly more efficient (the other one takes 50%-100% longer)
    """
    # n = instance.num_players
    # nturns = instance.max_winning_moves
    # nsuits = instance.num_suits
    # if k == 0:
    #     return \
    #     [ Or(ls.dummyturn[instance.max_winning_moves - 1], Not(ls.strike[m]))
    #         for m in range(first_turn, instance.max_winning_moves)] + \
    #     [ Or(ls.dummyturn[instance.max_winning_moves - 1], Not(ls.play5[m]),
    #           NotEquals(ls.clues[m - 1], Int(instance.max_clues)))
    #         for m in range(first_turn, instance.max_winning_moves)] + \
    #     [ Or(ls.dummyturn[instance.max_winning_moves - 1], *combination)
    #             for combination in itertools.combinations(
    #                 [ls.progress[instance.max_winning_moves - instance.num_players - 3, s, 5] for s in range(instance.num_suits)],
    #                 2 + instance.num_players // 5)]
    # else:
    #     return \
    #         [Implies(Or(ls.strike[m], And(ls.play5[m], Equals(ls.clues[m - 1], Int(instance.max_clues)))),Equals(ls.wasted_clue[m], ls.wasted_clue[m-1] + 1))
    #         for m in range(first_turn, nturns)] + \
    #         [Implies(Not(Or(ls.strike[m], And(ls.play5[m], Equals(ls.clues[m - 1], Int(instance.max_clues))))),Equals(ls.wasted_clue[m], ls.wasted_clue[m-1]))
    #         for m in range(first_turn, nturns)] + \
    #         [Implies(ls.progress[nturns - n - 3 - k, s, 5],Equals(ls.wasted_clue[nturns + s], ls.wasted_clue[nturns + s - 1]))
    #         for s in range(nsuits)] + \
    #         [Implies(Not(ls.progress[nturns - n - 3 - k, s, 5]),Equals(ls.wasted_clue[nturns + s], ls.wasted_clue[nturns + s - 1] + 1))
    #         for s in range(nsuits)] + \
    #         [Implies(And(Not(ls.dummyturn[nturns - 1 - k]), ls.dummyturn[nturns - k]), LE(ls.wasted_clue[nturns + nsuits - 1], Int(k + 1 + n // 5)))]

def solve_sat(starting_state: hanab_game.GameState | hanab_game.HanabiInstance, min_pace: Optional[int] = 0) -> Tuple[
    bool, Optional[hanab_game.GameState]]:
    if isinstance(starting_state, hanab_game.HanabiInstance):
        instance = starting_state
        game_state = hanab_game.GameState(instance)
    elif isinstance(starting_state, hanab_game.GameState):
        instance = starting_state.instance
        game_state = starting_state
    else:
        raise ValueError("Bad argument type")

    # print(f"{instance.num_dealt_cards}.")
    # for i in range(instance.deck_size):
    #     print(f"Drawing card {i} at score <= {max_score(instance, i)}, turn >= {min_turn(instance, i)} and pace <= {max_pace(instance, i)}.")
    vpool = IDPool()
    ls = Literals(vpool, instance)

    ##### setup of initial game state

    # properties used later to model valid moves

    starting_hands = [[card.deck_index for card in hand] for hand in game_state.hands]
    first_turn = len(game_state.actions)

    # Initialize solver
    cnf = CNF()

    # boundary conditions

    # start with 8 clues
    for i in range(-instance.clue_cost, instance.max_clues):
        cnf.append([ls.clues_gt[-1, i]])
    # cannot have > 8 clues.
    for m in range(-1, instance.max_winning_moves):
        cnf.append([-ls.clues_gt[m, instance.max_clues]])

    # start with 0 strikes
    for i in range(instance.num_strikes):
        cnf.append([-ls.strikes_gt[-1, i]])

    # first few turns are not extra turns / dummy turns
    for m in range(instance.draw_pile_size):
        cnf.append([-ls.extraturn[m]])
    for m in range(instance.draw_pile_size + instance.num_players):
        cnf.append([-ls.dummyturn[m]])

    # no cards can be played before turn 0
    for i in range(instance.deck_size):
        cnf.append([-ls.use_le[-1, i]])

    # initial cards are drawn before turn 0
    cnf.append([-ls.draw_ge[0, instance.num_dealt_cards - 1]])

    # other cards cannot be drawn too early
    # here we assume that all cards are drawn, which is not an issue
    # (we don't even stop the game at max score)
    for m in range(instance.deck_size - instance.num_dealt_cards):
        for i in range(instance.num_dealt_cards + m, instance.deck_size):
            cnf.append([ls.draw_ge[m, i]])

    # if i is drawn at turn `>= m+1`, then it is drawn at turn `>= m`
    for m in range(instance.max_winning_moves - 1):
        for i in range(instance.num_dealt_cards, instance.deck_size):
            cnf.append([-ls.draw_ge[m + 1, i], ls.draw_ge[m, i]])

    # if i is drawn at turn `>= m`, then `i + 1` is drawn at turn `>= m + 1`
    for m in range(instance.max_winning_moves - 1):
        for i in range(instance.num_dealt_cards, instance.deck_size - 1):
            cnf.append([-ls.draw_ge[m, i], ls.draw_ge[m + 1, i + 1]])

    # progress starts at 0
    for s in range(instance.num_suits):
        for r in range(1, 6):
            cnf.append([-ls.progress[-1, s, r]])

    # win condition
    for s in range(instance.num_suits):
        for r in range(1, 6):
            cnf.append([ls.progress[instance.max_winning_moves - 1, s, r]])

    # start with max pace
    cnf.append([-ls.pace_gt[-1, instance.initial_pace]])
    for i in range(-1, instance.initial_pace):
        cnf.append([ls.pace_gt[-1, i]])

    if isinstance(starting_state, hanab_game.GameState) and first_turn > 0:
        return False, None
        # TODO

        # set initial clues
        for i in range(instance.max_clues):
            if i < game_state.clues:
                cnf.append([ls.clues_gt[first_turn - 1, i]])
            else:
                cnf.append([-ls.clues_gt[first_turn - 1, i]])

        # set initial pace
        for i in range(-1, instance.initial_pace + 1):
            if i < game_state.pace:
                cnf.append([ls.pace_gt[first_turn - 1, i]])
            else:
                cnf.append([-ls.pace_gt[first_turn - 1, i]])

        # set initial strikes
        for i in range(instance.num_strikes):
            if i < game_state.strikes:
                cnf.append([ls.strikes_gt[first_turn - 1, i]])
            else:
                cnf.append([-ls.strikes_gt[first_turn - 1, i]])

        # check if extra round has started (not properly supported if it is)
        if game_state.remaining_extra_turns < game_state.num_players:
            cnf.append([ls.extraturn[first_turn - 1]])
        else:
            cnf.append([-ls.extraturn[first_turn - 1]])
        cnf.append([-ls.dummyturn[first_turn - 1]])

        # set recent draws: important to model progress
        # we just pretend that the last card drawn was in fact drawn last turn,
        # regardless of when it was actually drawn
        for neg_turn in range(1, min(9, first_turn + 2)):
            for i in range(instance.num_players * instance.hand_size, instance.deck_size):
                if neg_turn == 1 and i == game_state.progress - 1:
                    cnf.append([ls.draw[first_turn - neg_turn, i]])
                else:
                    cnf.append([-ls.draw[first_turn - neg_turn, i]])

        # forbid re-drawing of the last card drawn
        for m in range(first_turn, instance.max_winning_moves):
            cnf.append([-ls.draw[m, game_state.progress - 1]])

        # model initial progress
        for s in range(game_state.num_suits):
            for r in range(1, 6):
                if r <= game_state.stacks[s]:
                    cnf.append([ls.progress[first_turn - 1, s, r]])
                else:
                    cnf.append([-ls.progress[first_turn - 1, s, r]])


    ### Now, model all valid moves

    # for m in range(30):
    for m in range(instance.max_winning_moves):
        # in dummy turns, we assume you clue
        cnf.append([-ls.dummyturn[m], ls.clue[m]])

        # on every turn you clue or use a card, bot not both
        for i in range(instance.deck_size):
            cnf.append([-ls.clue[m], -ls.use[m, i]])
        cnf.append([ls.clue[m]] + [ls.use[m, i] for i in range(instance.deck_size)])

        # definition of draw_any
        for i in range(instance.num_dealt_cards, instance.deck_size):
            cnf.append([ls.draw_any[m], -ls.draw[m, i]])
        cnf.append([-ls.draw_any[m]] + [ls.draw[m, i] for i in range(instance.num_dealt_cards, instance.deck_size)])

        # you cannot both clue and draw a card
        cnf.append([-ls.clue[m], -ls.draw_any[m]])
        # you either clue, draw a card, or it is an extra turn
        cnf.append([ls.clue[m], ls.draw_any[m], ls.extraturn[m]])

        # you cannot both play and clue
        cnf.append([-ls.play[m], -ls.clue[m]])

        # definition of play5
        cnf.append([-ls.play5[m], ls.play[m]])
        for i in range(instance.deck_size):
            if instance.deck[i].rank == 5:
                cnf.append([ls.play5[m], -ls.play[m], -ls.use[m, i]])
        cnf.append([-ls.play5[m]] + [ls.use[m, i] for i in range(instance.deck_size) if instance.deck[i].rank == 5])

        # definition of incr_clues
        cnf.append([-ls.incr_clues[m], -ls.clue[m]])
        cnf.append([-ls.incr_clues[m], -ls.clues_gt[m - 1, instance.max_clues - 1]])
        cnf.append([-ls.incr_clues[m], -ls.play[m], ls.play5[m]])
        cnf.append([ls.incr_clues[m], ls.clue[m], ls.clues_gt[m - 1, instance.max_clues - 1], ls.play[m]])
        cnf.append([ls.incr_clues[m], ls.clue[m], ls.clues_gt[m - 1, instance.max_clues - 1], -ls.play5[m]])

        # if you have `> i + 1` clues, you have `> i` clues
        for i in range(-instance.clue_cost, instance.max_clues):
            cnf.append([-ls.clues_gt[m, i + 1], ls.clues_gt[m, i]])

        # clues are always nonnegative
        cnf.append([ls.clues_gt[m, -1]])
        # change of clues
        for i in range(instance.max_clues + 1):
            cnf.append([-ls.clues_gt[m - 1, i], ls.clues_gt[m, i - instance.clue_cost]]) # -ls.clue[m], ls.dummyturn[m],
            cnf.append([-ls.clue[m], ls.dummyturn[m], ls.clues_gt[m - 1, i], -ls.clues_gt[m, i - instance.clue_cost]])
            cnf.append([-ls.incr_clues[m], -ls.clues_gt[m - 1, i - 1], ls.clues_gt[m, i]])
            cnf.append([ls.clues_gt[m - 1, i - 1], -ls.clues_gt[m, i]]) # -ls.incr_clues[m],
            cnf.append([ls.incr_clues[m], ls.clue[m], -ls.clues_gt[m - 1, i], ls.clues_gt[m, i]])
            cnf.append([ls.incr_clues[m], ls.clue[m], ls.clues_gt[m - 1, i], -ls.clues_gt[m, i]])
            cnf.append([ls.incr_clues[m], -ls.dummyturn[m], -ls.clues_gt[m - 1, i], ls.clues_gt[m, i]])
            cnf.append([ls.incr_clues[m], -ls.dummyturn[m], ls.clues_gt[m - 1, i], -ls.clues_gt[m, i]])

        ## more than 8 clues not allowed, ls.use produces a strike
        # Note that this means that we will never strike while not at 8 clues.
        # It's easy to see that if there is any solution to the instance, then there is also one where we only strike at 8 clues
        # (or not at all) -> Just strike later if neccessary
        # So, we decrease the solution space with this formulation, but do not change whether it's empty or not

        # Note(F): I don't think we encode that strikes cannot happen with playable cards, but that should also preserve playability.
        cnf.append([-ls.strike[m], -ls.clue[m]])
        cnf.append([-ls.strike[m], -ls.play[m]])
        cnf.append([-ls.strike[m], ls.clues_gt[m - 1, instance.max_clues - 1]])
        cnf.append([ls.strike[m], ls.clue[m], ls.play[m], -ls.clues_gt[m - 1, instance.max_clues - 1]])

        # if you have `> i + 1` strikes, you have `> i` strikes
        for i in range(instance.num_strikes - 1):
            cnf.append([-ls.strikes_gt[m, i + 1], ls.strikes_gt[m, i]])

        # cannot have max strikes
        cnf.append([-ls.strikes_gt[m, instance.num_strikes - 1]])
        # change of strikes
        cnf.append([-ls.strike[m], ls.strikes_gt[m, 0]])
        for i in range(instance.num_strikes - 1):
            cnf.append([-ls.strikes_gt[m - 1, i], ls.strikes_gt[m, i]])
            cnf.append([ls.strikes_gt[m - 1, i], -ls.strikes_gt[m, i + 1]])
            cnf.append([-ls.strike[m], -ls.strikes_gt[m - 1, i], ls.strikes_gt[m, i + 1]])
            cnf.append([ls.strike[m], ls.strikes_gt[m - 1, i], -ls.strikes_gt[m, i]])

        # (there are some draw_ge clauses in the initial conditions)

        # you draw card i on turn m iff you draw it on turn m+ but not (m+1)+
        if m < instance.max_winning_moves - instance.num_players: # you cannot draw on the last few turns anyway
            for i in range(instance.num_dealt_cards, instance.deck_size):
                cnf.append([-ls.draw[m, i], ls.draw_ge[m, i]])
                cnf.append([-ls.draw[m, i], -ls.draw_ge[m+1, i]])
                cnf.append([ls.draw[m, i], -ls.draw_ge[m, i], ls.draw_ge[m+1, i]])

        # definition of use and use_le
        for i in range(instance.deck_size):
            cnf.append([-ls.use[m, i], ls.use_le[m, i]])
            cnf.append([-ls.use[m, i], -ls.use_le[m-1, i]])
            cnf.append([-ls.use_le[m-1, i], ls.use_le[m, i]])
            cnf.append([ls.use[m, i], ls.use_le[m-1, i], -ls.use_le[m, i]])

        # we can only use a card if we drew it earlier...
        for i in range(game_state.progress, instance.deck_size):
            cnf.append([-ls.use[m, i]] + [ls.draw[m0, i] for m0 in range(m - instance.num_players, first_turn - 1, -instance.num_players)])

        # ...or if it was part of the initial hand
        for i in range(game_state.progress):
            if i not in starting_hands[m % instance.num_players]:
                cnf.append([-ls.use[m, i]])

        useatmostone = CardEnc.atmost(lits=[ls.use[m, i] for i in range(instance.deck_size)], bound=1, encoding=1, vpool=vpool)
        cnf.extend(useatmostone)

        # (there are some progress clauses in the initial conditions)

        for s in range(instance.num_suits):
            for r in range(1, 5):
                # if progress `>= r + 1` on turn `m`, then `>= r` on turn `m-1`
                cnf.append([-ls.progress[m, s, r + 1], ls.progress[m - 1, s, r]])
            for r in range(1, 6):
                # if progress `>= r` on turn `m-1`, then also on turn `m`
                cnf.append([-ls.progress[m - 1, s, r], ls.progress[m, s, r]])
                # (from this it follows that if progress `>= r + 1`, then progress `>= r`)
                # required condition to increase progress
                cnf.append([ls.progress[m - 1, s, r], -ls.progress[m, s, r], ls.play[m]])
                cnf.append([ls.progress[m - 1, s, r], -ls.progress[m, s, r]] +
                    [ls.use[m, i] for i in range(instance.deck_size) if instance.deck[i] == hanab_game.DeckCard(s, r)])

        # we can only play a card if it matches the progress, and that advances the progress
        # (we could add a clause with `ls.progress[m - 1, s, r - 1]`, but that can be derived from this)
        for i in range(instance.deck_size):
            cnf.append([-ls.use[m, i], -ls.play[m], -ls.progress[m - 1, instance.deck[i].suitIndex, instance.deck[i].rank]])
            cnf.append([-ls.use[m, i], -ls.play[m], ls.progress[m, instance.deck[i].suitIndex, instance.deck[i].rank]])

        if m >= instance.draw_pile_size:
            # extra turns
            # cnf.append([ls.extraturn[instance.max_winning_moves - instance.num_players]])
            cnf.append([-ls.extraturn[m - 1], ls.extraturn[m]])
            cnf.append([-ls.draw[m - 1, instance.deck_size - 1], ls.extraturn[m]])
            cnf.append([-ls.extraturn[m], ls.extraturn[m - 1], ls.draw[m - 1, instance.deck_size - 1]])

            # dummy turns
            cnf.append([-ls.dummyturn[m - 1], ls.dummyturn[m]])
            cnf.append([-ls.extraturn[m - instance.num_players], ls.dummyturn[m]])
            cnf.append([-ls.dummyturn[m], ls.dummyturn[m - 1], ls.extraturn[m - instance.num_players]])

        for i in range(-1, instance.initial_pace + 1):
            # if pace `>= i` on turn `m`, then also on turn `m - 1`
            cnf.append([-ls.pace_gt[m, i], ls.pace_gt[m - 1, i]])
            # if you play or clue, then pace doesn't change
            cnf.append([-ls.play[m], ls.pace_gt[m, i], -ls.pace_gt[m - 1, i]])
            cnf.append([-ls.clue[m], ls.pace_gt[m, i], -ls.pace_gt[m - 1, i]])

        for i in range(-1, instance.initial_pace):
            # if pace `>= i + 1` on turn `m - 1`, then it is `>= i` on turn `m`
            cnf.append([-ls.pace_gt[m - 1, i + 1], ls.pace_gt[m, i]])
            # if you don't play or clue, pace decreases by 1
            cnf.append([ls.clue[m], ls.play[m], ls.pace_gt[m - 1, i + 1], -ls.pace_gt[m, i]])

        # (From this it follows that if you have pace `>= i + 1`, you have pace `>= i`)

        # pace is nonnegative
        cnf.append([ls.pace_gt[m, 0], ls.extraturn[m]])
        if m <= 34:
            cnf.append([ls.pace_gt[m, 0]])

    ## extra constraints that help the solver

    # cards cannot be drawn too late
    for m in range(instance.max_winning_moves):
        for i in range(instance.num_dealt_cards, instance.deck_size - max(0, instance.max_winning_moves - instance.num_players - m)):
            cnf.append([-ls.draw_ge[m, i]])

    # played every color/value combination (NOTE: redundant, but makes solving faster)
    # *[
    #     Or(
    #         And(ls.use[m, i], ls.play[m])
    #         for m in range(first_turn, instance.max_winning_moves)
    #         for i in range(instance.deck_size)
    #         if game_state.deck[i] == hanab_game.DeckCard(s, r)
    #     )
    #     for s in range(instance.num_suits)
    #     for r in range(1, 6)
    #     if r > game_state.stacks[s]
    # ],

    # pace constraints
    # *pace_constraints(instance, ls, first_turn),

    # max-turns constraint: we can add extra conditions on a game at almost the maximum number of turns
    # *game_length_constraints(instance, ls, first_turn, 0),
    # *game_length_constraints(instance, ls, first_turn, 1),

    # earliest possible draws of cards if (almost) max turns
    # *[
    #     Or(ls.dummyturn[instance.max_winning_moves - 1 - k], ls.draw_on_or_after[min_turn(instance, i, k), i])
    #     for i in range(instance.num_dealt_cards, instance.deck_size)
    #     for k in range(2)
    # ],

    ## EXTRA CONDITION. This can be used to check whether
    ## the SAT-solver can disprove a particular statement.
    # Not(ls.draw_on_or_after[27, 39]),
    # Not(ls.dummyturn[instance.max_winning_moves - 4]),
    # ls.dummyturn[instance.max_winning_moves - 4],
    # Not(ls.draw_on_or_after[15, 32]), #easy
    # Not(ls.draw_on_or_after[20, 37]), #easy
    # Not(ls.draw_on_or_after[25, 39]), # to do this, we need to encode "score >= k when card i is drawn" in a variable.
    # ls.progress[44, 1, 4],
    # ls.progress[1, 0, 1],
    # Not(ls.use[49, 18]),
    # ls.use[49, 18],
    # Not(ls.use[48, 38]),
    # Not(ls.use[48, 42]),
    # Not(ls.use[47, 38]),
    # Not(ls.use[47, 42]),
    # Not(ls.use[50, 0]),
    # ls.play[51],
    # Not(ls.-clue[instance.max_winning_moves - 2]),
    # Not(ls.use[m, i]),
    # cnf.append([ls.clue[0]])
    # cnf.append([ls.clue[1]])
    # cnf.append([ls.clue[2]])
    # cnf.append([-ls.clue[3]])
    # cnf.append([-ls.clue[4]])
    # cnf.append([-ls.clue[5]])
    # cnf.append([ls.clue[6]])
    # cnf.append([-ls.clue[7]])
    # cnf.append([-ls.clue[8]])
    # cnf.append([ls.clue[9]])
    # cnf.append([-ls.clue[10]])
    # cnf.append([-ls.clue[11]])
    # cnf.append([ls.clue[12]])
    # cnf.append([ls.clue[13]])
    # cnf.append([ls.clue[14]])
    # cnf.append([-ls.clue[15]])
    # cnf.append([-ls.clue[16]])
    # cnf.append([-ls.clue[17]])
    # cnf.append([-ls.clue[18]])
    # cnf.append([-ls.clue[19]])
    # cnf.append([ls.clue[20]])
    # cnf.append([ls.clue[21]])
    # cnf.append([-ls.clue[22]])
    # cnf.append([-ls.clue[23]])
    # cnf.append([-ls.clue[24]])
    # cnf.append([-ls.clue[25]])
    # cnf.append([ls.clue[26]])
    # cnf.append([ls.clue[27]])
    # cnf.append([-ls.clue[28]])
    # cnf.append([-ls.clue[29]])
    # cnf.append([ls.clue[30]])
    # cnf.append([-ls.clue[31]])
    # cnf.append([ls.clue[32]])
    # cnf.append([-ls.clue[33]])
    # cnf.append([ls.clue[34]])
    # cnf.append([ls.clue[35]])
    # cnf.append([-ls.clue[36]])
    # cnf.append([ls.clue[37]])
    # cnf.append([ls.clue[38]])
    # cnf.append([-ls.clue[39]])
    # cnf.append([-ls.clue[40]])
    # cnf.append([-ls.clue[41]])

    # cnf.append([-ls.play[3]])
    # cnf.append([-ls.play[4]])
    # cnf.append([ls.play[5]])
    # cnf.append([-ls.play[7]])
    # cnf.append([ls.play[8]])
    # cnf.append([ls.play[10]])
    # cnf.append([-ls.play[11]])
    # cnf.append([-ls.play[15]])
    # cnf.append([-ls.play[16]])
    # cnf.append([ls.play[17]])
    # cnf.append([ls.play[18]])
    # cnf.append([-ls.play[19]])
    # cnf.append([-ls.play[22]])
    # cnf.append([ls.play[23]])
    # cnf.append([-ls.play[24]])
    # cnf.append([-ls.play[25]])
    # cnf.append([ls.play[28]])
    # cnf.append([ls.play[29]])
    # cnf.append([ls.play[31]])
    # cnf.append([ls.play[33]])
    # cnf.append([ls.play[36]])
    # cnf.append([ls.play[39]])
    # cnf.append([ls.play[40]])
    # cnf.append([ls.play[41]])
    # cnf.append([ls.play[42]])


    # print(cnf.clauses)
    cnf.to_file(f"hanabi_{instance.num_players}.cnf")
    # units = set(l[0] for l in cnf.clauses if len(l) == 1)
    # for u in units:
    #     if -u in units:
    #         print(f"Conflict: {vpool.obj(abs(u))}, {u}")
    # for i, clause in enumerate(cnf.clauses):
    #     if len(clause) == 0:
    #         print(f"Empty clause at index {i}")

    solver = Glucose42(bootstrap_with=cnf, with_proof=True)
    # print("Starting solver...")
    if solver.solve():
        raw_model = solver.get_model()
        model = {abs(i) : i > 0 for i in raw_model}
        for i in range(1, vpool.top + 1):
            if i not in model:
                model[i] = True
        # print(model)
        # print("SAT")
        log_model(model, game_state, ls)
        solution = evaluate_model(model, copy.deepcopy(game_state), ls)
        return True, solution
    else:
        # print("UNSAT")
        # print(solver.get_proof())
        with open("proof.txt", "w") as f:
            f.write(str(solver.get_proof()))
        return False, None

def log_model(model, cur_game_state, ls: Literals):
    deck = cur_game_state.deck
    first_turn = len(cur_game_state.actions)
    if first_turn > 0:
        logger.debug(f"[print_model] Note: Omitting first {first_turn} turns, since they were fixed already.")
    for m in range(first_turn, cur_game_state.instance.max_winning_moves):
        logger.debug(f"=== move {m} ===")
        logger.debug(f"clues: {len([i for i in range(cur_game_state.instance.max_clues) if model[ls.clues_gt[m, i]]])}, {[i for i in range(-1, cur_game_state.instance.max_clues + 1) if model[ls.clues_gt[m, i]]]}, {[i for i in range(-1, cur_game_state.instance.max_clues + 1) if not model[ls.clues_gt[m, i]]]}")
        logger.debug(f"strikes: {len([i for i in range(cur_game_state.instance.num_strikes) if model[ls.strikes_gt[m, i]]])}")
        logger.debug("draw: " + ", ".join(
            f"{i}: {deck[i]}" for i in range(cur_game_state.progress, cur_game_state.instance.deck_size) if
            model[ls.draw[m, i]]))
        # logger.debug("draw_ge: " + ", ".join(
        #     f"{i}: {deck[i]}" for i in range(cur_game_state.progress, cur_game_state.instance.deck_size) if
        #     model[ls.draw_ge[m, i]]))
        logger.debug("use: " + ", ".join(
            f"{i}: {deck[i]}" for i in range(cur_game_state.instance.deck_size) if
            model[ls.use[m, i]]))
        logger.debug(f"pace: {len([i for i in range(cur_game_state.instance.initial_pace) if model[ls.pace_gt[m, i]]])}")
        logger.debug(f"progress: " + "".join(
                f"{len([r for r in range(1, 6) if model[ls.progress[m, s, r]]])}" for s in range(cur_game_state.instance.num_suits)))
        # for s in range(cur_game_state.instance.num_suits):
        #     logger.debug(f"progress {constants.COLOR_INITIALS[s]}: " + "".join(
        #         str(r) for r in range(1, 6) if model[ls.progress[m, s, r]]))
        flags = ["clue", "draw_any", "play", "play5", "incr_clues", "strike", "extraturn", "dummyturn"]
        logger.debug(", ".join(f for f in flags if model[getattr(ls, f)[m]]))


# given the initial game state and the model found by the SAT solver,
# evaluates the model to produce a full game history
def evaluate_model(model, cur_game_state: hanab_game.GameState, ls: Literals) -> hanab_game.GameState:
    for m in range(len(cur_game_state.actions), cur_game_state.instance.max_winning_moves):
        if model[ls.dummyturn[m]] or cur_game_state.is_over():
            break
        if not model[ls.clue[m]]:
            card_idx = next(i for i in range(cur_game_state.instance.deck_size) if model[ls.use[m, i]])
            if model[ls.play[m]] or model[ls.strike[m]]:
                # print(m, model[ls.play[m]], model[ls.strike[m]], card_idx, cur_game_state.instance.deck[card_idx])
                cur_game_state.play(card_idx)
            else:
                cur_game_state.discard(card_idx)
        else:
            cur_game_state.clue()

    # for m in range(cur_game_state.instance.max_winning_moves):
    #     for i in range(cur_game_state.instance.deck_size):
    #         if model[ls.use[m, i]]:
    #             print(m, i)
    return cur_game_state
