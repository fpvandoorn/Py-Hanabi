from pysmt.shortcuts import Symbol, Bool, Not, Implies, Iff, And, Or, AtMostOne, ExactlyOne, get_model, get_atoms, get_formula_size, get_unsat_core
from pysmt.rewritings import conjunctive_partition
import json
MOVES = 60
NUM_STRIKES = 3
NUM_PLAYERS = 5

colors = 'rygbp'
deck_str = 'p5 p3 b4 r5 y4 y4 y5 r4 b2 y2 y3 g5 g2 g3 g4 p4 r3 b2 b3 b3 p4 b1 p2 b1 b1 p2 p1 p1 g1 r4 g1 r1 r3 r1 g1 r1 p1 b4 p3 g2 g3 g4 b5 y1 y1 y1 r2 r2 y2 y3'
deck = [(s[0], int(s[1])) for s in deck_str.split(' ')]

# clues[m][i] == "after move m we have at least i clues"
clues = {-1: {i: Bool(i < 9) for i in range(0, 10)}, **{m: {0: Bool(True), 9: Bool(False), **{i: Symbol('m{}c{}'.format(m, i)) for i in range(1, 9)}} for m in range(MOVES)}}
# strikes[m][i] == "after move m we have at least i strikes"
strikes = {-1: {i: Bool(i == 0) for i in range(0,NUM_STRIKES+1)}, **{m: {0: Bool(True), NUM_STRIKES: Bool(False), **{s: Symbol('m{}s{}'.format(m,s)) for s in range(1,NUM_STRIKES)}} for m in range(MOVES)} }
# extraround[m][i] == "after move m, the extraround has started and at least i turns of it have taken place"
# extraround = {28: {i: Bool(False) for i in range(0, NUM_PLAYERS)}, **{m: {NUM_PLAYERS+1: Bool(False), **{e: Symbol('m{}e{}'.format(m,t) for e in range(0, NUM_PLAYERS+1)}} for m in range(MOVES)} }
# extraturn[m] = "turn m is a move part of the extra round or a dummy turn"
extraround = {-1: Bool(False), **{m: Symbol('m{}e'.format(m)) for m in range(0, MOVES)}}
# dummyturn[m] = "turn m is a dummy nurn and not actually part of the game"
dummyturn = {-1: Bool(False), **{m: Symbol('m{}dt'.format(m)) for m in range(0, MOVES)}}
# strike[m] = "at move m we get a strike"
strike = {-1: Bool(False), **{m: Symbol('m{}s+'.format(m)) for m in range(MOVES)}}
# draw[m][i] == "at move m we draw deck[i]"
draw = {-1: {i: Bool(i == 19) for i in range(19, 50)}, **{m: {19: Bool(False), **{i: Symbol('m{}+{}'.format(m, i)) for i in range(20, 50)}} for m in range(MOVES)}}
# draw[m][i] == "at move m we play/discard deck[i]"
discard = {m: {i: Symbol('m{}-{}'.format(m, i)) for i in range(50)} for m in range(MOVES)}
# progress[m][c, k] == "after move m we have played in color c until k"
progress = {-1: {(c, k): Bool(k == 0) for c in colors for k in range(6)}, **{m: {**{(c, 0): Bool(True) for c in colors}, **{(c, k): Symbol('m{}:{}{}'.format(m, c, k)) for c in colors for k in range(1, 6)}} for m in range(MOVES)}}
# discard_any[m] == "at move m we play/discard a card"
discard_any = {m: Symbol('m{}d'.format(m)) for m in range(MOVES)}
# draw_any[m] == "at move m we draw a card"
draw_any = {m: Symbol('m{}D'.format(m)) for m in range(MOVES)}
# play[m] == "at move m we play a card"
play = {m: Symbol('m{}p'.format(m)) for m in range(MOVES)}
# play5[m] == "at move m we play a 5"
play5 = {m: Symbol('m{}p5'.format(m)) for m in range(MOVES)}
# incr_clues[m] == "at move m we obtain a clue"
incr_clues = {m: Symbol('m{}c+'.format(m)) for m in range(MOVES)}

def print_model(model):
    for m in range(MOVES):
        print('=== move {} ==='.format(m))
        print('clues: ' + ''.join(str(i) for i in range(1, 9) if model.get_py_value(clues[m][i])))
        print('strikes: ' + ''.join(str(i) for i in range(1, NUM_STRIKES) if model.get_py_value(strikes[m][i])))
        print('draw: ' + ', '.join('{} [{}{}]'.format(i, deck[i][0], deck[i][1]) for i in range(20, 50) if model.get_py_value(draw[m][i])))
        print('discard: ' + ', '.join('{} [{}{}]'.format(i, deck[i][0], deck[i][1]) for i in range(50) if model.get_py_value(discard[m][i])))
        for c in colors:
            print('progress {}: '.format(c) + ''.join(str(k) for k in range(1, 6) if model.get_py_value(progress[m][c, k])))
        flags = ['discard_any', 'draw_any', 'play', 'play5', 'incr_clues', 'strike', 'extraround', 'dummyturn']
        print(', '.join(f for f in flags if model.get_py_value(globals()[f][m])))

def toJSON(model):
    deck_json = [{"suitIndex": colors.index(s), "rank": r} for (s,r) in deck]
    players = ["Alice", "Bob", "Cathy", "Donald", "Emily"]
    hands = [deck[4*p:4*(p+1)] for p in range(0,5)]
    actions = []
    for m in range(MOVES):
        if model.get_py_value(dummyturn[m]):
            break
        if model.get_py_value(discard_any[m]):
            discarded = next(i for i in range(0,50) if model.get_py_value(discard[m][i]))
            icard = hands[m % 5].index(deck[discarded])
            for i in range(icard, 3):
                hands[m % 5][i] = hands[m % 5][i + 1]
            if model.get_py_value(draw_any[m]):
                hands[m % 5][3] = next(deck[i] for i in range(20, 50) if model.get_py_value(draw[m][i]))
            if model.get_py_value(play[m]) or model.get_py_value(strike[m]):
                actions.append({
                    "type": 0,
                    "target": discarded
                    })
            else:
                actions.append({
                    "type": 1,
                    "target": discarded
                    })
        else:
            actions.append({
                "type": 3,
                "target": (m + 1) % 5,
                "value": hands[(m+1) % 5][0][1]
                })
    actions.append({
        "type": 4,
        "value": 1
        })
    game = {
            "deck": deck_json,
            "players": players,
            "actions": actions,
            "first_player": 0,
            "options": {
                "variant": "No Variant",
                }
            }
    print(json.dumps(game))

valid_move = lambda m: And(
    Implies(dummyturn[m], Not(discard_any[m])),
    # definition of discard_any
    Iff(discard_any[m], Or(discard[m][i] for i in range(50))),
    # definition of draw_any
    Iff(draw_any[m], Or(draw[m][i] for i in range(20, 50))),
    # draw implies discard (and converse true before last 5 moves)
    Implies(draw_any[m], discard_any[m]),
    Implies(discard_any[m], Or(extraround[m], draw_any[m])),
    # play requires discard
    Implies(play[m], discard_any[m]),
    # definition of play5
    Iff(play5[m], And(play[m], Or(discard[m][i] for i in range(50) if deck[i][1] == 5))),
    # definition of incr_clues
    Iff(incr_clues[m], And(discard_any[m], Implies(play[m], And(play5[m], Not(clues[m-1][8]))))),
    #Iff(incr_clues[m], And(discard_any[m], Implies(play[m], play5[m]))),
    # change of clues
    *[Iff(clues[m][i], Or(clues[m-1][i+1], And(clues[m-1][i], Or(discard_any[m], dummyturn[m])), And(clues[m-1][i-1], incr_clues[m]))) for i in range(1, 9)],
    ## more than 8 clues not allowed, discarding produces a strike
    Iff(strike[m], And(discard_any[m], Not(play[m]), clues[m-1][8])),
    # change of strikes
    *[Iff(strikes[m][i], Or(strikes[m-1][i], And(strikes[m-1][i-1], strike[m]))) for i in range(1, NUM_STRIKES+1)],
    # less than 0 clues not allowed
    Implies(Not(discard_any[m]), Or(clues[m-1][1], dummyturn[m])),
    # we can only draw card i if the last drawn card was i-1
    *[Implies(draw[m][i], Or(And(draw[m0][i-1], *[Not(draw_any[m1]) for m1 in range(m0+1, m)]) for m0 in range(max(-1, m-9), m))) for i in range(20, 50)],
    #*[Implies(draw[m][i], Not(draw[m0][i])) for m0 in range(m) for i in range(20, 50)],
    #*[Implies(draw[m][i], Or(draw[m0][i-1] for m0 in range(max(-1, m-9), m))) for i in range(20, 50)],
    # we can only draw at most one card (NOTE: redundant, FIXME: avoid quadratic formula)
    AtMostOne(draw[m][i] for i in range(20, 50)),
    #*[Not(And(draw[m][i], draw[m][j])) for i in range(20, 50) for j in range(20, i)],
    # we can only discard a card if we drew it earlier...
    *[Implies(discard[m][i], Or(draw[m0][i] for m0 in range(m-5, -1, -5))) for i in range(20, 50)],
    # ...or if it was part of the initial hand
    *[Not(discard[m][i]) for i in range(20) if i//4 != m%5],
    # we can only discard a card if we did not discard it yet
    *[Implies(discard[m][i], And(Not(discard[m0][i]) for m0 in range(m-5, -1, -5))) for i in range(50)],
    # we can only discard at most one card (FIXME: avoid quadratic formula)
    AtMostOne(discard[m][i] for i in range(50)),
    #*[Not(And(discard[m][i], discard[m][j])) for i in range(50) for j in range(i)],
    # we can only play a card if it matches the progress
    *[Implies(And(discard[m][i], play[m]), And(Not(progress[m-1][deck[i]]), progress[m-1][deck[i][0], deck[i][1]-1])) for i in range(50)],
    # change of progress
    *[Iff(progress[m][c, k], Or(progress[m-1][c, k], And(play[m], Or(discard[m][i] for i in range(50) if deck[i] == (c, k))))) for c in colors for k in range(1, 6)],
    # extra round bool
    Iff(extraround[m], Or(extraround[m-1], draw[m-1][49])),
    # dummy turn bool
    *[Iff(dummyturn[m], Or(dummyturn[m-1], draw[m-6][49])) for i in range(0,1) if m >= 5]
)

win = And(
    # maximum progress at each color
    *[progress[MOVES-1][c, 5] for c in colors],
    # played every color/value combination (NOTE: redundant)
    *[Or(And(discard[m][i], play[m]) for m in range(MOVES) for i in range(50) if deck[i] == (c, k)) for c in colors for k in range(1, 6)]
)

constraints = And(*[valid_move(m) for m in range(MOVES)], win)
print('{} variables, {} nodes'.format(len(get_atoms(constraints)), get_formula_size(constraints)))

model = get_model(constraints)
if model:
    print_model(model)
    toJSON(model)
else:
    print('unsatisfiable')
    #conj = list(conjunctive_partition(constraints))
    #print('statements: {}'.format(len(conj)))
    #ucore = get_unsat_core(conj)
    #print('unsat core size: {}'.format(len(ucore)))
    #for f in ucore:
    #    print(f.serialize())
