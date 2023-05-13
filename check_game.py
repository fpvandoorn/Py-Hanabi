import copy
from typing import Tuple, Optional

from database import conn
from compress import decompress_deck, decompress_actions, compress_actions, link
from hanabi import Action, GameState
from hanab_live import HanabLiveInstance, HanabLiveGameState
from sat import solve_sat
from download_data import export_game


# returns number of first turn before which the game was infeasible (counting from 0)
# and a replay achieving maximum score (from this turn onwards) if instance is feasible
# 0 if instance is infeasible
# 1 if instance is feasible but first turn is suboptimal
# ...
# (number of turns) if replay was winning
def check_game(game_id: int) -> Tuple[int, GameState]:
    with conn.cursor() as cur:
        cur.execute("SELECT games.num_players, deck, actions, score, games.variant_id FROM games "
                    "INNER JOIN seeds ON seeds.seed = games.seed "
                    "WHERE games.id = (%s)",
                    (game_id,)
                    )
        (num_players, compressed_deck, compressed_actions, score, variant_id) = cur.fetchone()
        deck = decompress_deck(compressed_deck)
        actions = decompress_actions(compressed_actions)

        instance = HanabLiveInstance(deck, num_players, variant_id=variant_id)

        if instance.max_score == score:
            # instance has been won, nothing to compute here
            return len(actions)
        
        # store the turn numbers *before* we know the game was (in)feasible
        solvable_turn = 0
        unsolvable_turn = len(actions)

        # first, check if the instance itself is feasible:
        game = HanabLiveGameState(instance)
        solvable, solution = solve_sat(game)
        if not solvable:
            return 0, solution

        while unsolvable_turn - solvable_turn > 1:
            try_turn = (unsolvable_turn + solvable_turn) // 2
            try_game = copy.deepcopy(game)
            assert(len(try_game.actions) == solvable_turn)
            for a in range(solvable_turn, try_turn):
                try_game.make_action(actions[a])
            solvable, potential_sol = solve_sat(try_game)
            if solvable:
                solution = potential_sol
                game = try_game
                solvable_turn = try_turn
            else:
                unsolvable_turn = try_turn

        assert(unsolvable_turn - 1 == solvable_turn)
        return unsolvable_turn, solution


if __name__ == "__main__":
    game_id = 921269
    export_game(game_id)
    print("checking game {}".format(game_id))
    turn, sol = check_game(game_id)
    if turn != 0:
        print(turn, link(sol))
    else:
        print("instance is unfeasible")
    pass
