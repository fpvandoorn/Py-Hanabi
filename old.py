
def print_suits_and_attrs():
    with open("variants.json") as f:
        variants = json.loads(f.read())
    x = set()
    c = []
    for var in variants:
        for k in var.keys():
            x.add(k)
        for s in var['suits']:
            if s not in c:
                c.append(s)
    for y in x:
        print(y)
    print()

    for s in c:
        print(s)

    attributes = {
        "nativeColors": ["Red"],
        "ranks": 1,  # 0: none, 1: default, 2: all
        "colors": 1,  # 0: none, 1: default, 2: all, 3: prism
        "dark": False,
        "reversed": False,
        "prism": False
    }

    d = OrderedDict((s, attributes) for s in c)

    if not os.path.isfile("colors.json"):
        with open("colors.json", "w") as f:
            f.writelines(json.dumps(d, indent=4, sort_keys=False))

    # need: suit name -> colors


def create_suit_graph():
    with open("variants.json") as f:
        variants = json.loads(f.read())
    G = nx.DiGraph()
    for var in variants:
        suits = var['suits']
        for suit in suits:
            if suit not in G.nodes:
                G.add_node(suit)
        for i in range(0, len(suits) - 1):
            G.add_edge(suits[i], suits[i + 1], var=var['name'])

    H = nx.DiGraph()
    try:
        while True:
            cycle = nx.find_cycle(G)
            #            J = nx.DiGraph()
            #            J.add_edges_from(cycle)
            #            nx.draw(J, with_labels=True)
            H.add_edges_from(cycle)
            G.remove_edges_from(cycle)
    except nx.NetworkXNoCycle:
        pass

    nx.draw(H, with_labels=True, font_weight='bold')
    plt.show()
