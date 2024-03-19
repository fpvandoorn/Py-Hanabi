import copy
from typing import Tuple

from hanabi import logger
from hanabi import database
from hanabi import hanab_game
from hanabi.live import hanab_live
from hanabi.live import compress
from hanabi.solvers import sat

from hanabi.database import games_db_interface


# returns minimal number T of turns (from game) after which instance was infeasible
# and a replay achieving maximum score while following the replay for the first (T-1) turns:
# if instance is feasible, returns number of turns + 1
# returns 0 if instance is infeasible
# returns 1 if instance is feasible but first turn is suboptimal
# ...
# # turns + 1 if the final state is still winning
def check_game(game_id: int) -> Tuple[int, hanab_game.GameState]:
    logger.debug("Analysing game {}".format(game_id))
    with database.conn.cursor() as cur:
        cur.execute("SELECT games.num_players, score, games.variant_id, starting_player FROM games "
                    "WHERE games.id = (%s)",
                    (game_id,)
                    )
        res = cur.fetchone()
        if res is None:
            raise ValueError("No game associated with id {} in database.".format(game_id))
        (num_players, score, variant_id, starting_player) = res
        instance, actions = games_db_interface.load_game_parts(game_id)

        # check if the instance is already won
        if instance.max_score == score:
            game = hanab_live.HanabLiveGameState(instance)
            for action in actions:
                game.make_action(action)
            # instance has been won, nothing to compute here
            return len(actions) + 1, game

        # first, check if the instance itself is feasible:
        game = hanab_live.HanabLiveGameState(instance)
        solvable, solution = sat.solve_sat(game)
        if not solvable:
            return 0, solution
        logger.verbose("Instance {} is feasible after 0 turns: {}".format(game_id, compress.link(solution)))

        # store lower and upper bounds of numbers of turns after which we know the game was feasible / infeasible
        solvable_turn = 0
        unsolvable_turn = len(actions)

        while unsolvable_turn - solvable_turn > 1:
            try_turn = (unsolvable_turn + solvable_turn) // 2
            try_game = copy.deepcopy(game)
            assert len(try_game.actions) == solvable_turn
            for a in range(solvable_turn, try_turn):
                try_game.make_action(actions[a])
            logger.debug("Checking if instance {} is feasible after {} turns.".format(game_id, try_turn))
            solvable, potential_sol = sat.solve_sat(try_game)
            if solvable:
                solution = potential_sol
                game = try_game
                solvable_turn = try_turn
                logger.verbose("Instance {} is feasible after {} turns: {}#{}"
                               .format(game_id, solvable_turn, compress.link(solution), solvable_turn + 1))
            else:
                unsolvable_turn = try_turn
                logger.verbose("Instance {} is not feasible after {} turns.".format(game_id, unsolvable_turn))

        assert unsolvable_turn - 1 == solvable_turn
        return unsolvable_turn, solution
