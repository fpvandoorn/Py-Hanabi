import copy
from pysmt.shortcuts import Symbol, Bool, Not, Implies, Iff, And, Or, AtMostOne, ExactlyOne, get_model, get_atoms, get_formula_size, get_unsat_core, Equals, GE, NotEquals, Int
from pysmt.typing import INT
from pysmt.rewritings import conjunctive_partition
import json
from typing import List, Optional, Tuple
from concurrent.futures import ProcessPoolExecutor

from hanabi import DeckCard, Action, ActionType, GameState, HanabiInstance
from compress import link, decompress_deck
from greedy_solver import GreedyStrategy
from constants import COLOR_INITIALS
from log_setup import logger


# literals to model game as sat instance to check for feasibility
# variants 'throw it in a hole not handled', 'clue starved' and 'up or down' currently not handled
class Literals():
    # num_suits is total number of suits, i.e. also counts the dark suits
    # default distribution among all suits is assumed
    def __init__(self, instance: HanabiInstance):

        # clues[m][i] == "after move m we have i clues", in clue starved, this counts half clues
        self.clues = {
                -1: Int(16 if instance.clue_starved else 8)  # we have 8 clues after turn
                , **{
                        m: Symbol('m{}clues'.format(m), INT)
                        for m in range(instance.max_winning_moves)
                    }
                }

        self.pace = {
            -1: Int(instance.initial_pace)
            , **{
                m: Symbol('m{}pace'.format(m), INT)
                for m in range(instance.max_winning_moves)
            }
        }

        # strikes[m][i] == "after move m we have at least i strikes"
        self.strikes = {
                    -1: {i: Bool(i == 0) for i in range(0, instance.num_strikes + 1)}    # no strikes when we start
                  , **{
                          m: {
                              0: Bool(True),
                              **{ s: Symbol('m{}strikes{}'.format(m,s)) for s in range(1, instance.num_strikes) },
                              instance.num_strikes: Bool(False)                              # never so many clues that we lose. Implicitly forbids striking out
                             }
                          for m in range(instance.max_winning_moves)
                      }
                  }

        # extraturn[m] = "turn m is a move part of the extra round or a dummy turn"
        self.extraround = {
                     -1: Bool(False)
                     , **{
                             m: Bool(False) if m < instance.draw_pile_size else Symbol('m{}extra'.format(m))   # it takes at least as many turns as cards in the draw pile to start the extra round
                             for m in range(0, instance.max_winning_moves)
                         }
                     }

        # dummyturn[m] = "turn m is a dummy nurn and not actually part of the game"
        self.dummyturn = {
                    -1: Bool(False)
                    , **{
                            m: Bool(False) if m < instance.draw_pile_size + instance.num_players else Symbol('m{}dummy'.format(m))
                            for m in range(0, instance.max_winning_moves)
                        }
                    }

        # draw[m][i] == "at move m we play/discard deck[i]"
        self.discard = {
                    m: {i: Symbol('m{}discard{}'.format(m, i)) for i in range(instance.deck_size)}
                    for m in range(instance.max_winning_moves)
                  }

        # draw[m][i] == "at move m we draw deck card i"
        self.draw = {
                -1: { i: Bool(i == instance.num_dealt_cards - 1) for i in range(instance.num_dealt_cards - 1, instance.deck_size) }
                , **{
                        m: {
                            instance.num_dealt_cards - 1: Bool(False),
                            **{i: Symbol('m{}draw{}'.format(m, i)) for i in range(instance.num_dealt_cards, instance.deck_size)}
                            }
                        for m in range(instance.max_winning_moves)
                    }
               }

        # strike[m] = "at move m we get a strike"
        self.strike = {
                 -1: Bool(False)
                 , **{
                        m: Symbol('m{}newstrike'.format(m))
                        for m in range(instance.max_winning_moves)
                     }
                 }

        # progress[m][card = (suitIndex, rank)] == "after move m we have played in suitIndex up to rank"
        self.progress = {
                     -1: {(s, r): Bool(r == 0) for s in range(0, instance.num_suits) for r in range(0, 6)} # at start, have only played rank zero
                   , **{
                           m: {
                               **{(s, 0): Bool(True) for s in range(0, instance.num_suits)},
                               **{(s, r): Symbol('m{}progress{}{}'.format(m, s, r)) for s in range(0, instance.num_suits) for r in range(1, 6)}
                              }
                           for m in range(instance.max_winning_moves)
                       }
                   }

        ## Utility variables

        # discard_any[m] == "at move m we play/discard a card"
        self.discard_any = { m: Symbol('m{}discard_any'.format(m)) for m in range(instance.max_winning_moves) }

        # draw_any[m] == "at move m we draw a card"
        self.draw_any = {m: Symbol('m{}draw_any'.format(m)) for m in range(instance.max_winning_moves)}

        # play[m] == "at move m we play a card"
        self.play = {m: Symbol('m{}play'.format(m)) for m in range(instance.max_winning_moves)}

        # play5[m] == "at move m we play a 5"
        self.play5 = {m: Symbol('m{}play5'.format(m)) for m in range(instance.max_winning_moves)}

        # incr_clues[m] == "at move m we obtain a clue"
        self.incr_clues = {m: Symbol('m{}c+'.format(m)) for m in range(instance.max_winning_moves)}


def solve_sat(starting_state: GameState | HanabiInstance, min_pace: Optional[int] = 0) -> Tuple[bool, Optional[GameState]]:
    if isinstance(starting_state, HanabiInstance):
        instance = starting_state
        game_state = GameState(instance)
    elif isinstance(starting_state, GameState):
        instance = starting_state.instance
        game_state = starting_state
    else:
        raise ValueError("Bad argument type")

    ls = Literals(instance)

    ##### setup of initial game state

    # properties used later to model valid moves

    starting_hands = [[card.deck_index for card in hand] for hand in game_state.hands]
    first_turn = len(game_state.actions)

    if isinstance(starting_state, GameState):
        # have to set additional variables

        # set initial clues
        for i in range(0, 10):
            ls.clues[first_turn - 1] = Int(game_state.clues)

        # set initial pace
        ls.pace[first_turn - 1] = Int(game_state.pace)

        # set initial strikes
        for i in range(0, instance.num_strikes + 1):
            ls.strikes[first_turn - 1][i] = Bool(i <= game_state.strikes)

        # check if extraround has started (usually not)
        ls.extraround[first_turn - 1] = Bool(game_state.remaining_extra_turns < game_state.num_players)
        ls.dummyturn[first_turn -1] = Bool(False)

        # set recent draws: important to model progress
        # we just pretend that the last card drawn was in fact drawn last turn,
        # regardless of when it was actually drawn
        for neg_turn in range(1, min(9, first_turn + 2)):
            for i in range(instance.num_players * instance.hand_size, instance.deck_size):
                ls.draw[first_turn - neg_turn][i] = Bool(neg_turn == 1 and i == game_state.progress - 1)
        # forbid re-drawing of the last card drawn
        for m in range(first_turn, instance.max_winning_moves):
            ls.draw[m][game_state.progress - 1] = Bool(False)


        # model initial progress
        for s in range(0, game_state.num_suits):
            for r in range(0, 6):
                ls.progress[first_turn - 1][s, r] = Bool(r <= game_state.stacks[s])

    ### Now, model all valid moves

    valid_move = lambda m: And(
        # in dummy turns, nothing can be discarded
        Implies(ls.dummyturn[m], Not(ls.discard_any[m])),

        # definition of discard_any
        Iff(ls.discard_any[m], Or(ls.discard[m][i] for i in range(instance.deck_size))),

        # definition of draw_any
        Iff(ls.draw_any[m], Or(ls.draw[m][i] for i in range(game_state.progress, instance.deck_size))),

        # ls.draw implies ls.discard (and converse true before the ls.extraround)
        Implies(ls.draw_any[m], ls.discard_any[m]),
        Implies(ls.discard_any[m], Or(ls.extraround[m], ls.draw_any[m])),

        # ls.play requires ls.discard
        Implies(ls.play[m], ls.discard_any[m]),

        # definition of ls.play5
        Iff(ls.play5[m], And(ls.play[m], Or(ls.discard[m][i] for i in range(instance.deck_size) if instance.deck[i].rank == 5))),

        # definition of ls.incr_clues
        Iff(ls.incr_clues[m], And(ls.discard_any[m], NotEquals(ls.clues[m-1], Int(16 if instance.clue_starved else 8)), Implies(ls.play[m], ls.play5[m]))),

        # change of ls.clues
        Implies(And(Not(ls.discard_any[m]), Not(ls.dummyturn[m])),
                Equals(ls.clues[m], ls.clues[m-1] - (2 if instance.clue_starved else 1))),
        Implies(ls.incr_clues[m], Equals(ls.clues[m], ls.clues[m-1] + 1)),
        Implies(And(Or(ls.discard_any[m], ls.dummyturn[m]), Not(ls.incr_clues[m])), Equals(ls.clues[m], ls.clues[m-1])),

        # change of pace
        Implies(And(ls.discard_any[m], Or(ls.strike[m], Not(ls.play[m]))), Equals(ls.pace[m], ls.pace[m-1] - 1)),
        Implies(Or(Not(ls.discard_any[m]), And(Not(ls.strike[m]), ls.play[m])), Equals(ls.pace[m], ls.pace[m-1])),

        # pace is nonnegative
        GE(ls.pace[m], Int(min_pace)),

        ## more than 8 clues not allowed, ls.discarding produces a strike
        # Note that this means that we will never strike while not at 8 clues.
        # It's easy to see that if there is any solution to the instance, then there is also one where we only strike at 8 clues
        # (or not at all) -> Just strike later if neccessary
        # So, we decrease the solution space with this formulation, but do not change whether it's empty or not
        Iff(ls.strike[m], And(ls.discard_any[m], Not(ls.play[m]), Equals(ls.clues[m-1], Int(16 if instance.clue_starved else 8)))),

        # change of strikes
        *[Iff(ls.strikes[m][i], Or(ls.strikes[m-1][i], And(ls.strikes[m-1][i-1], ls.strike[m]))) for i in range(1, instance.num_strikes + 1)],

        # less than 0 clues not allowed
        Implies(Not(ls.discard_any[m]), Or(GE(ls.clues[m-1], Int(1)), ls.dummyturn[m])),

        # we can only draw card i if the last ls.drawn card was i-1
        *[Implies(ls.draw[m][i], Or(And(ls.draw[m0][i-1], *[Not(ls.draw_any[m1]) for m1 in range(m0+1, m)]) for m0 in range(max(first_turn - 1, m-9), m))) for i in range(game_state.progress, instance.deck_size)],

        # we can only draw at most one card (NOTE: redundant, FIXME: avoid quadratic formula)
        AtMostOne(ls.draw[m][i] for i in range(game_state.progress, instance.deck_size)),

        # we can only discard a card if we drew it earlier...
        *[Implies(ls.discard[m][i], Or(ls.draw[m0][i] for m0 in range(m-instance.num_players, first_turn - 1, -instance.num_players))) for i in range(game_state.progress, instance.deck_size)],

        # ...or if it was part of the initial hand
        *[Not(ls.discard[m][i]) for i in range(0, game_state.progress) if i not in starting_hands[m % instance.num_players] ],

        # we can only discard a card if we did not discard it yet
        *[Implies(ls.discard[m][i], And(Not(ls.discard[m0][i]) for m0 in range(m-instance.num_players, first_turn - 1, -instance.num_players))) for i in range(instance.deck_size)],

        # we can only discard at most one card (FIXME: avoid quadratic formula)
        AtMostOne(ls.discard[m][i] for i in range(instance.deck_size)),

        # we can only play a card if it matches the progress
        *[Implies(
                    And(ls.discard[m][i], ls.play[m]),
                    And(
                        Not(ls.progress[m-1][instance.deck[i].suitIndex, instance.deck[i].rank]),
                        ls.progress[m-1][instance.deck[i].suitIndex, instance.deck[i].rank-1 ]
                       )
                  )
          for i in range(instance.deck_size)
          ],

        # change of progress
        *[
            Iff(
                ls.progress[m][s, r],
                Or(
                    ls.progress[m-1][s, r],
                    And(ls.play[m], Or(ls.discard[m][i]
                        for i in range(0, instance.deck_size)
                        if instance.deck[i] == DeckCard(s, r) ))
                  )
                )
            for s in range(0, instance.num_suits)
            for r in range(1, 6)
         ],

        # extra round bool
        Iff(ls.extraround[m], Or(ls.extraround[m-1], ls.draw[m-1][instance.deck_size-1])),

        # dummy turn bool
        *[Iff(ls.dummyturn[m], Or(ls.dummyturn[m-1], ls.draw[m-1 - instance.num_players][instance.deck_size-1])) for i in range(0,1) if m >= instance.num_players]
    )

    win = And(
        # maximum progress at each color
        *[ls.progress[instance.max_winning_moves-1][s, 5] for s in range(0, instance.num_suits)],

        # played every color/value combination (NOTE: redundant, but makes solving faster)
        *[
            Or(
               And(ls.discard[m][i], ls.play[m])
               for m in range(first_turn, instance.max_winning_moves)
               for i in range(instance.deck_size)
               if game_state.deck[i] == DeckCard(s, r)
              )
          for s in range(0, instance.num_suits)
          for r in range(1, 6)
          if r > game_state.stacks[s]
          ]
    )

    constraints = And(*[valid_move(m) for m in range(first_turn, instance.max_winning_moves)], win)
#    print('Solving instance with {} variables, {} nodes'.format(len(get_atoms(constraints)), get_formula_size(constraints)))

    model = get_model(constraints)
    if model:
        log_model(model, game_state, ls)
        solution = evaluate_model(model, copy.deepcopy(game_state), ls)
        return True, solution
    else:
        #conj = list(conjunctive_partition(constraints))
        #print('statements: {}'.format(len(conj)))
        #ucore = get_unsat_core(conj)
        #print('unsat core size: {}'.format(len(ucore)))
        #for f in ucore:
        #    print(f.serialize())
        return False, None


def log_model(model, cur_game_state, ls: Literals):
    deck = cur_game_state.deck
    first_turn = len(cur_game_state.actions)
    if first_turn > 0:
        logger.debug('[print_model] Note: Omitting first {} turns, since they were fixed already.'.format(first_turn))
    for m in range(first_turn, cur_game_state.instance.max_winning_moves):
        logger.debug('=== move {} ==='.format(m))
        logger.debug('clues: {}'.format(model.get_py_value(ls.clues[m])))
        logger.debug('strikes: ' + ''.join(str(i) for i in range(1, 3) if model.get_py_value(ls.strikes[m][i])))
        logger.debug('draw: ' + ', '.join('{}: {}'.format(i, deck[i]) for i in range(cur_game_state.progress, cur_game_state.instance.deck_size) if model.get_py_value(ls.draw[m][i])))
        logger.debug('discard: ' + ', '.join('{}: {}'.format(i, deck[i]) for i in range(cur_game_state.instance.deck_size) if model.get_py_value(ls.discard[m][i])))
        logger.debug('pace: {}'.format(model.get_py_value(ls.pace[m])))
        for s in range(0, cur_game_state.instance.num_suits):
            logger.debug('progress {}: '.format(COLOR_INITIALS[s]) + ''.join(str(r) for r in range(1, 6) if model.get_py_value(ls.progress[m][s, r])))
        flags = ['discard_any', 'draw_any', 'play', 'play5', 'incr_clues', 'strike', 'extraround', 'dummyturn']
        logger.debug(', '.join(f for f in flags if model.get_py_value(getattr(ls, f)[m])))



# given the initial game state and the model found by the SAT solver,
# evaluates the model to produce a full game history
def evaluate_model(model, cur_game_state: GameState, ls: Literals) -> GameState:
    for m in range(len(cur_game_state.actions), cur_game_state.instance.max_winning_moves):
        if model.get_py_value(ls.dummyturn[m]) or cur_game_state.is_over():
            break
        if model.get_py_value(ls.discard_any[m]):
            card_idx = next(i for i in range(0, cur_game_state.instance.deck_size) if model.get_py_value(ls.discard[m][i]))
            if model.get_py_value(ls.play[m]) or model.get_py_value(ls.strike[m]):
                cur_game_state.play(card_idx)
            else:
                cur_game_state.discard(card_idx)
        else:
            cur_game_state.clue()

    return cur_game_state



def run_deck():
    puzzle = True
    if puzzle:
        deck_str = 'p5 p3 b4 r5 y4 y4 y5 r4 b2 y2 y3 g5 g2 g3 g4 p4 r3 b2 b3 b3 p4 b1 p2 b1 b1 p2 p1 p1 g1 r4 g1 r1 r3 r1 g1 r1 p1 b4 p3 g2 g3 g4 b5 y1 y1 y1 r2 r2 y2 y3'

        deck = [DeckCard(COLOR_INITIALS.index(c[0]), int(c[1])) for c in deck_str.split(" ")]
        num_p = 5
    else:
        deck_str = "15gfvqluvuwaqnmrkpkaignlaxpjbmsprksfcddeybfixchuhtwo"
        deck_str = "15diuknfwhqbplsrlkxjuvfbwyacoaxgtudcerskqfnhpgampmiv"
        deck_str = "15jdxlpobvikrnhkslcuwggimtphafquqfvcwadampxkeyfrbnsu"
        deck = decompress_deck(deck_str)
        num_p = 6

    print(deck)

    gs = GameState(HanabiInstance(deck, num_p))
    if puzzle:
        gs.play(2)
    else:
        strat = GreedyStrategy(gs)
        for _ in range(17):
            strat.make_move()

    solvable, sol = solve_sat(gs, 0)
    if solvable:
        print(sol)
        print(link(sol))
    else:
        print('unsolvable')

if __name__ == "__main__":
    run_deck()
