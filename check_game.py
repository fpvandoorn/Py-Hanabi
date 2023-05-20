import copy
from typing import Tuple, Optional

import verboselogs

from database.database import conn
from compress import decompress_deck, decompress_actions, compress_actions, link
from hanabi import Action, GameState
from hanab_live import HanabLiveInstance, HanabLiveGameState
from sat import solve_sat
from log_setup import logger, logger_manager
from download_data import detailed_export_game


# returns minimal number T of turns (from game) after which instance was infeasible
# and a replay achieving maximum score while following the replay for the first (T-1) turns:
# if instance is feasible, returns number of turns + 1
# returns 0 if instance is infeasible
# returns 1 if instance is feasible but first turn is suboptimal
# ...
# # turns + 1 if the final state is still winning
def check_game(game_id: int) -> Tuple[int, GameState]:
    logger.debug("Analysing game {}".format(game_id))
    with conn.cursor() as cur:
        cur.execute("SELECT games.num_players, deck, actions, score, games.variant_id FROM games "
                    "INNER JOIN seeds ON seeds.seed = games.seed "
                    "WHERE games.id = (%s)",
                    (game_id,)
                    )
        res = cur.fetchone()
        if res is None:
            raise ValueError("No game associated with id {} in database.".format(game_id))
        (num_players, compressed_deck, compressed_actions, score, variant_id) = res
        deck = decompress_deck(compressed_deck)
        actions = decompress_actions(compressed_actions)

        instance = HanabLiveInstance(deck, num_players, variant_id=variant_id)

        if instance.max_score == score:
            game = HanabLiveGameState(instance)
            for action in actions:
                game.make_action(action)
            # instance has been won, nothing to compute here
            return len(actions) + 1, game
        
        # store lower and upper bounds of numbers of turns after which we know the game was feasible / infeasible
        solvable_turn = 0
        unsolvable_turn = len(actions)

        # first, check if the instance itself is feasible:
        game = HanabLiveGameState(instance)
        solvable, solution = solve_sat(game)
        if not solvable:
            logger.debug("Returning: Instance {} is not feasible")
            return 0, solution
        logger.verbose("Instance {} is feasible after 0 turns: {}".format(game_id, link(solution)))

        while unsolvable_turn - solvable_turn > 1:
            try_turn = (unsolvable_turn + solvable_turn) // 2
            try_game = copy.deepcopy(game)
            assert(len(try_game.actions) == solvable_turn)
            for a in range(solvable_turn, try_turn):
                try_game.make_action(actions[a])
            logger.debug("Checking if instance {} is feasible after {} turs".format(game_id, try_turn))
            solvable, potential_sol = solve_sat(try_game)
            if solvable:
                solution = potential_sol
                game = try_game
                solvable_turn = try_turn
                logger.verbose("Instance {} is feasible after {} turns: {}".format(game_id, solvable_turn, link(solution)))
            else:
                unsolvable_turn = try_turn
                logger.verbose("Instance {} is not feasible after {} turns".format(game_id, unsolvable_turn))

        assert unsolvable_turn - 1 == solvable_turn, "Programming error"
        return unsolvable_turn, solution
