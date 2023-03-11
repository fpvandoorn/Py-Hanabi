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
