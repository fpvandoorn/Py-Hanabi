import json


# Some setup for conversion between variant id and name
with open("variants.json", 'r') as f:
    VARIANTS = json.loads(f.read())

def variant_id(variant_name):
    return next(var['id'] for var in VARIANTS if var['name'] == variant_name)

def variant_name(variant_id):
    return next(var['name'] for var in VARIANTS if var['id'] == variant_id)

def num_suits(variant_id):
    return next(len(var['suits']) for var in VARIANTS if var['id'] == variant_id)

def properties(variant_id):
    return next(var for var in VARIANTS if var['id'] == variant_id)


if __name__ == "__main__":
    x = set()
    c = set()
    for var in VARIANTS:
        for k in var.keys():
            x.add(k)
        for s in var['suits']:
            c.add(s)
    for y in x:
        print(y)

    for s in c:
        print(s)

    # need: suit name -> colors

"""
# actual changes of theoretical instance
clueStarved
throwItInHole (no clues for fives)

# general restrictions on what clues are allowed
alternatingClues
clueColors
clueRanks
synesthesia (no rank clused, but color touches rank as well)

# can be ignored
cowPig
duck

# -> use oracle?
# clue touch changed
chimneys
funnels
colorCluesTouchNothing
rankCluesTouchNothing
oddsAndEvens (ranks touch ranks of same parity)

# changes behaviour of ones or fives
specialAllClueColors
specialAllClueRanks
specialNoClueColors
specialNoClueRanks
specialDeceptive
specialRank

upOrDown
criticalFours
"""
