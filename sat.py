from pysmt.shortcuts import Symbol, Bool, Not, Implies, Iff, And, Or, AtMostOne, ExactlyOne, get_model, get_atoms, get_formula_size, get_unsat_core
from pysmt.rewritings import conjunctive_partition
import json
from typing import List
from concurrent.futures import ProcessPoolExecutor

from compress import DeckCard, Action, ActionType, link
from greedy_solver import GameState

COLORS = 'rygbp'
STANDARD_HAND_SIZE = {2: 5, 3: 5, 4: 4, 5: 4, 6: 3}
NUM_STRIKES_TO_LOSE = 3


# literals to model game as sat instance to check for feasibility
# variants 'throw it in a hole not handled', 'clue starved' and 'up or down' currently not handled
class Literals():
    # num_suits is total number of suits, i.e. also counts the dark suits
    # default distribution among all suits is assumed
    def __init__(self, num_players, num_suits, num_dark_suits=0):
        assert ( 2 <= num_players <= 6 )

        ## some game parameters
        self.num_players = num_players
        self.num_suits = num_suits
        self.num_dark_suits = num_dark_suits

        self.hand_size = STANDARD_HAND_SIZE[num_players]
        self.num_strikes = NUM_STRIKES_TO_LOSE
        self.deck_size = 10 * num_suits - 5 * num_dark_suits
        self.distributed_cards = self.num_players * self.hand_size
        self.draw_pile_size = self.deck_size - self.distributed_cards

        ## maximum number of moves in any game that can achieve max score
        # each suit gives 15 moves, as we can play and discard 5 cards each and give 5 clues. dark suits only give 5 moves, since no discards are added
        # number of cards that remain in players hands after end of game. they cost 2 turns each, since we cannot discard them and also have one clue less
        # 8 clues at beginning, one further clue for each suit but one (the clue of the last 5 is never useful since it is gained in the extra-round)
        # subtract a further move for a second 5-clue that can't be used in 5 or 6-player games, since the extraround starts too soon
        self.max_moves = 15 * num_suits - 10 * num_dark_suits    \
                        - 2 * num_players * (self.hand_size - 1) \
                        + 8 + (num_suits - 1)                    \
                        + (-1 if num_players >= 5 else 0)

        ###
        # note that we generate 'literals' always one out of boundary and set them to explicit truth values. This makes sat formulation easier but has no actual overhead in solving it
        # move are numbered starting with 0

        # clues[m][i] == "after move m we have at least i clues"
        self.clues = {
                -1: { i: Bool(i < 9) for i in range(0, 10) }  # we have 8 clues after turn -1
                , **{
                        m: {
                            0: Bool(True),                                                # always at least 0 clues
                            **{ i: Symbol('m{}c{}'.format(m, i)) for i in range(1, 9) },
                            9: Bool(False)                                                # never 9 or more clues. This will implicitly forbid discarding at 8 clues later
                           }
                        for m in range(self.max_moves)
                    }
                }

        # strikes[m][i] == "after move m we have at least i strikes"
        self.strikes = {
                    -1: {i: Bool(i == 0) for i in range(0, self.num_strikes + 1)}    # no strikes when we start
                  , **{
                          m: {
                              0: Bool(True),
                              **{ s: Symbol('m{}s{}'.format(m,s)) for s in range(1, self.num_strikes) },
                              self.num_strikes: Bool(False)                              # never so many clues that we lose. Implicitly forbids striking out
                             }
                          for m in range(self.max_moves)
                      }
                  }

        # extraturn[m] = "turn m is a move part of the extra round or a dummy turn"
        self.extraround = {
                     -1: Bool(False)
                     , **{
                             m: Bool(False) if m < self.draw_pile_size else Symbol('m{}e'.format(m))   # it takes at least as many turns as cards in the draw pile to start the extra round
                             for m in range(0, self.max_moves)
                         }
                     }

        # dummyturn[m] = "turn m is a dummy nurn and not actually part of the game"
        self.dummyturn = {
                    -1: Bool(False)
                    , **{
                            m: Bool(False) if m < self.draw_pile_size + self.num_players else Symbol('m{}dt'.format(m))
                            for m in range(0, self.max_moves)
                        }
                    }

        # draw[m][i] == "at move m we play/discard deck[i]"
        self.discard = {
                    m: {i: Symbol('m{}-{}'.format(m, i)) for i in range(self.deck_size)}
                    for m in range(self.max_moves)
                  }

        # draw[m][i] == "at move m we draw deck card i"
        self.draw = {
                -1: { i: Bool(i == self.distributed_cards - 1) for i in range(self.distributed_cards - 1, self.deck_size) }
                , **{
                        m: {
                            self.distributed_cards - 1: Bool(False),
                            **{i: Symbol('m{}+{}'.format(m, i)) for i in range(self.distributed_cards, self.deck_size)}
                            }
                        for m in range(self.max_moves)
                    }
               }

        # strike[m] = "at move m we get a strike"
        self.strike = {
                 -1: Bool(False)
                 , **{
                        m: Symbol('m{}s+'.format(m))
                        for m in range(self.max_moves)
                     }
                 }

        # progress[m][card = (suitIndex, rank)] == "after move m we have played in suitIndex up to rank"
        self.progress = {
                     -1: {(s, r): Bool(r == 0) for s in range(0, self.num_suits) for r in range(0, 6)} # at start, have only played rank zero
                   , **{
                           m: {
                               **{(s, 0): Bool(True) for s in range(0, self.num_suits)},
                               **{(s, r): Symbol('m{}:{}{}'.format(m, s, r)) for s in range(0, self.num_suits) for r in range(1, 6)}
                              }
                           for m in range(self.max_moves)
                       }
                   }

        ## Utility variables

        # discard_any[m] == "at move m we play/discard a card"
        self.discard_any = { m: Symbol('m{}d'.format(m)) for m in range(self.max_moves) }

        # draw_any[m] == "at move m we draw a card"
        self.draw_any = {m: Symbol('m{}D'.format(m)) for m in range(self.max_moves)}

        # play[m] == "at move m we play a card"
        self.play = {m: Symbol('m{}p'.format(m)) for m in range(self.max_moves)}

        # play5[m] == "at move m we play a 5"
        self.play5 = {m: Symbol('m{}p5'.format(m)) for m in range(self.max_moves)}

        # incr_clues[m] == "at move m we obtain a clue"
        self.incr_clues = {m: Symbol('m{}c+'.format(m)) for m in range(self.max_moves)}



def solve(deck: List[DeckCard], num_players=5):

    num_suits = max(map(lambda card: card.suitIndex, deck)) + 1
    num_dark_suits = (len(deck) - 10 * num_suits) // (-5)

    ls = Literals(num_players, num_suits, num_dark_suits)

    valid_move = lambda m: And(
        # in dummy turns, nothing can be discarded
        Implies(ls.dummyturn[m], Not(ls.discard_any[m])),

        # definition of discard_any
        Iff(ls.discard_any[m], Or(ls.discard[m][i] for i in range(ls.deck_size))),

        # definition of draw_any
        Iff(ls.draw_any[m], Or(ls.draw[m][i] for i in range(ls.distributed_cards, ls.deck_size))),

        # ls.draw implies ls.discard (and converse true before the ls.extraround)
        Implies(ls.draw_any[m], ls.discard_any[m]),
        Implies(ls.discard_any[m], Or(ls.extraround[m], ls.draw_any[m])),

        # ls.play requires ls.discard
        Implies(ls.play[m], ls.discard_any[m]),

        # definition of ls.play5
        Iff(ls.play5[m], And(ls.play[m], Or(ls.discard[m][i] for i in range(ls.deck_size) if deck[i].rank == 5))),

        # definition of ls.incr_clues
        Iff(ls.incr_clues[m], And(ls.discard_any[m], Implies(ls.play[m], And(ls.play5[m], Not(ls.clues[m-1][8]))))),

        # change of ls.clues
        *[Iff(ls.clues[m][i], Or(ls.clues[m-1][i+1], And(ls.clues[m-1][i], Or(ls.discard_any[m], ls.dummyturn[m])), And(ls.clues[m-1][i-1], ls.incr_clues[m]))) for i in range(1, 9)],

        ## more than 8 clues not allowed, ls.discarding produces a strike
        # Note that this means that we will never strike while not at 8 clues.
        # It's easy to see that if there is any solution to the instance, then there is also one where we only strike at 8 clues
        # (or not at all) -> Just strike later if neccessary
        # So, we decrease the solution space with this formulation, but do not change whether it's empty or not
        Iff(ls.strike[m], And(ls.discard_any[m], Not(ls.play[m]), ls.clues[m-1][8])),

        # change of strikes
        *[Iff(ls.strikes[m][i], Or(ls.strikes[m-1][i], And(ls.strikes[m-1][i-1], ls.strike[m]))) for i in range(1, ls.num_strikes + 1)],

        # less than 0 clues not allowed
        Implies(Not(ls.discard_any[m]), Or(ls.clues[m-1][1], ls.dummyturn[m])),

        # we can only draw card i if the last ls.drawn card was i-1
        *[Implies(ls.draw[m][i], Or(And(ls.draw[m0][i-1], *[Not(ls.draw_any[m1]) for m1 in range(m0+1, m)]) for m0 in range(max(-1, m-9), m))) for i in range(ls.distributed_cards, ls.deck_size)],

        # we can only draw at most one card (NOTE: redundant, FIXME: avoid quadratic formula)
        AtMostOne(ls.draw[m][i] for i in range(ls.distributed_cards, ls.deck_size)),

        # we can only discard a card if we drew it earlier...
        *[Implies(ls.discard[m][i], Or(ls.draw[m0][i] for m0 in range(m-ls.num_players, -1, -ls.num_players))) for i in range(ls.distributed_cards, ls.deck_size)],

        # ...or if it was part of the initial hand
        *[Not(ls.discard[m][i]) for i in range(0, ls.distributed_cards) if i // ls.hand_size != m % ls.num_players],

        # we can only discard a card if we did not discard it yet
        *[Implies(ls.discard[m][i], And(Not(ls.discard[m0][i]) for m0 in range(m-ls.num_players, -1, -ls.num_players))) for i in range(ls.deck_size)],

        # we can only discard at most one card (FIXME: avoid quadratic formula)
        AtMostOne(ls.discard[m][i] for i in range(ls.deck_size)),

        # we can only play a card if it matches the progress
        *[Implies(
                    And(ls.discard[m][i], ls.play[m]),
                    And(
                        Not(ls.progress[m-1][deck[i].suitIndex, deck[i].rank]),
                        ls.progress[m-1][deck[i].suitIndex, deck[i].rank-1 ]
                       )
                  )
          for i in range(ls.deck_size)
          ],

        # change of progress
        *[
            Iff(
                ls.progress[m][s, r],
                Or(
                    ls.progress[m-1][s, r],
                    And(ls.play[m], Or(ls.discard[m][i]
                        for i in range(0, ls.deck_size)
                        if deck[i] == DeckCard(s, r) ))
                  )
                )
            for s in range(0, ls.num_suits)
            for r in range(1, 6)
         ],

        # extra round bool
        Iff(ls.extraround[m], Or(ls.extraround[m-1], ls.draw[m-1][ls.deck_size-1])),

        # dummy turn bool
        *[Iff(ls.dummyturn[m], Or(ls.dummyturn[m-1], ls.draw[m-1 - ls.num_players][ls.deck_size-1])) for i in range(0,1) if m >= ls.num_players]
    )

    win = And(
        # maximum progress at each color
        *[ls.progress[ls.max_moves-1][s, 5] for s in range(0, ls.num_suits)],

        # played every color/value combination (NOTE: redundant, but makes solving faster)
        *[
            Or(
               And(ls.discard[m][i], ls.play[m])
               for m in range(ls.max_moves)
               for i in range(ls.deck_size)
               if deck[i] == DeckCard(s, r)
              )
          for s in range(0, ls.num_suits)
          for r in range(1, 6)
          ]
    )

    constraints = And(*[valid_move(m) for m in range(ls.max_moves)], win)
#    print('Solving instance with {} variables, {} nodes'.format(len(get_atoms(constraints)), get_formula_size(constraints)))

    model = get_model(constraints)
    if model:
#        print_model(model, deck)
        solution = toJSON(model, deck, ls)
        return True, solution
    else:
        return False, None
        #conj = list(conjunctive_partition(constraints))
        #print('statements: {}'.format(len(conj)))
        #ucore = get_unsat_core(conj)
        #print('unsat core size: {}'.format(len(ucore)))
        #for f in ucore:
        #    print(f.serialize())

def print_model(model, deck, num_players):
    draw = globals()['draw'][num_players]
    for m in range(max_moves[num_players]):
        print('=== move {} ==='.format(m))
        print('clues: ' + ''.join(str(i) for i in range(1, 9) if model.get_py_value(clues[m][i])))
        print('strikes: ' + ''.join(str(i) for i in range(1, NUM_STRIKES) if model.get_py_value(strikes[m][i])))
        print('draw: ' + ', '.join('{} [{}{}]'.format(i, deck[i][0], deck[i][1]) for i in range(20, 50) if model.get_py_value(draw[m][i])))
        print('discard: ' + ', '.join('{} [{}{}]'.format(i, deck[i][0], deck[i][1]) for i in range(50) if model.get_py_value(discard[m][i])))
        for c in COLORS:
            print('progress {}: '.format(c) + ''.join(str(k) for k in range(1, 6) if model.get_py_value(progress[m][c, k])))
        flags = ['discard_any', 'draw_any', 'play', 'play5', 'incr_clues', 'strike', 'extraround', 'dummyturn']
        print(', '.join(f for f in flags if model.get_py_value(globals()[f][m])))


def toJSON(model, deck: List[DeckCard], ls: Literals) -> dict:
    gs = GameState(ls.num_players, deck)

    for m in range(ls.max_moves):
        if model.get_py_value(ls.dummyturn[m]):
            break
        if model.get_py_value(ls.discard_any[m]):
            card_idx = next(i for i in range(0, ls.deck_size) if model.get_py_value(ls.discard[m][i]))
            if model.get_py_value(ls.play[m]) or model.get_py_value(ls.strike[m]):
                gs.play(card_idx)
            else:
                gs.discard(card_idx)
        else:
            gs.clue()

    return gs.to_json()

def run_deck():
    deck_str = 'p5 p3 b4 r5 y4 y4 y5 r4 b2 y2 y3 g5 g2 g3 g4 p4 r3 b2 b3 b3 p4 b1 p2 b1 b1 p2 p1 p1 g1 r4 g1 r1 r3 r1 g1 r1 p1 b4 p3 g2 g3 g4 b5 y1 y1 y1 r2 r2 y2 y3'

    deck = [DeckCard(COLORS.index(c[0]), int(c[1])) for c in deck_str.split(" ")]
    print(deck)

    solvable, sol = solve(deck, num_players=5)
    if solvable:
        print(sol)
        print(link(sol))

if __name__ == "__main__":
    run_deck()
