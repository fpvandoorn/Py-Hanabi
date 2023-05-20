#! /usr/bin/python3

import argparse
import logging

import verboselogs

from check_game import check_game
from download_data import detailed_export_game
from compress import link
from log_setup import logger, logger_manager

"""
init db + populate tables
download games of variant
download single game
analyze single game
"""


def add_init_subparser(subparsers):
    parser = subparsers.add_parser(
        'init',
        help='Init database tables, retrieve variant and suit information from hanab.live'
    )


def add_download_subparser(subparsers):
    parser = subparsers.add_parser('download', help='Download games from hanab.live')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--var', '-v', type=int)
    group.add_argument('--id', '-i', type=int)


def add_analyze_subparser(subparsers):
    parser = subparsers.add_parser('analyze', help='Analyze a game and find the last winning state')
    parser.add_argument('game_id', type=int)
    parser.add_argument('--download', '-d', help='Download game if not in database', action='store_true')


def analyze_game(game_id: int, download: bool = False):
    if download:
        detailed_export_game(game_id)
    logger.info('Analyzing game {}'.format(game_id))
    turn, sol = check_game(game_id)
    if turn == 0:
        logger.info('Instance is unfeasible')
    else:
        logger.info('Game was first lost after {} turns.'.format(turn))
        logger.info(
            'A replay achieving perfect score from the previous turn onwards is: {}#{}'
            .format(link(sol), turn)
        )


def main_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='hanabi_suite',
        description='High-level interface for analysis of hanabi instances.'
    )
    subparsers = parser.add_subparsers(dest='command', required=True, help='select subcommand')

    add_init_subparser(subparsers)
    add_analyze_subparser(subparsers)
    add_download_subparser(subparsers)

    return parser


if __name__ == "__main__":
    args = main_parser().parse_args()
    switcher = {
        'analyze': analyze_game
    }
    method_args = dict(vars(args))
    method_args.pop('command')
    switcher[args.command](**method_args)
