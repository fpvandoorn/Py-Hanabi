import argparse
from typing import Optional

import verboselogs

from hanabi import logger, logger_manager
from hanabi.live import variants
from hanabi.live import check_game
from hanabi.live import download_data
from hanabi.live import compress
from hanabi.database import init_database

"""
init db + populate tables
download games of variant
download single game
analyze single game
"""


def subcommand_analyze(game_id: int, download: bool = False):
    if download:
        download_data.detailed_export_game(game_id)
    logger.info('Analyzing game {}'.format(game_id))
    turn, sol = check_game.check_game(game_id)
    if turn == 0:
        logger.info('Instance is unfeasible')
    else:
        logger.info('Game was first lost after {} turns.'.format(turn))
        logger.info(
            'A replay achieving perfect score from the previous turn onwards is: {}#{}'
            .format(compress.link(sol), turn)
        )


def subcommand_init(force: bool, populate: bool):
    tables = init_database.get_existing_tables()
    if len(tables) > 0 and not force:
        logger.info(
            'Database tables "{}" exist already, aborting. To force re-initialization, use the --force options'
            .format(", ".join(tables))
        )
        return
    if len(tables) > 0:
        logger.info(
            "WARNING: This will drop all existing tables from the database and re-initialize them."
        )
        response = input("Do you wish to continue? [y/N] ")
        if response not in ["y", "Y", "yes"]:
            return
    init_database.init_database_tables()
    logger.info("Successfully initialized database tables")
    if populate:
        init_database.populate_static_tables()
        logger.info("Successfully populated tables with variants and suits from hanab.live")


def subcommand_download(
          game_id: Optional[int]
        , variant_id: Optional[int]
        , export_all: bool = False
        , all_variants: bool = False
):
    if game_id is not None:
        download_data.detailed_export_game(game_id)
        logger.info("Successfully exported game ")
    if variant_id is not None:
        download_data.download_games(variant_id, export_all)
        logger.info("Successfully exported games for variant id {}".format(variant_id))
    if all_variants:
        for variant in variants.get_all_variant_ids():
            download_data.download_games(variant, export_all)
        logger.info("Successfully exported games for all variants")


def add_init_subparser(subparsers):
    parser = subparsers.add_parser(
        'init',
        help='Init database tables, retrieve variant and suit information from hanab.live'
    )
    parser.add_argument('--force', '-f', help='Force initialization (Drops existing tables)', action='store_true')
    parser.add_argument(
        '--no-populate-tables', '-n',
        help='Do not download variant and suit information from hanab.live',
        action='store_false',
        dest='populate'
    )


def add_download_subparser(subparsers):
    parser = subparsers.add_parser('download', help='Download games from hanab.live')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        '--var', '--variant', '-v',
        type=int,
        dest='variant_id',
        help='Download information on all games given variant id (but not necessarily export all of them)'
    )
    group.add_argument('--id', '-i', type=int, dest='game_id', help='Download single game given id')
    group.add_argument(
        '--all-variants', '-a',
        action='store_true',
        dest='all_variants',
        help='Download information from games on all variants (but not necessarily export all of them)'
    )
    parser.add_argument(
        '--export-all', '-e',
        action='store_true',
        dest='export_all',
        help='Export all games specified in full detail (i.e. also actions and game options)'
    )


def add_analyze_subparser(subparsers):
    parser = subparsers.add_parser('analyze', help='Analyze a game and find the last winning state')
    parser.add_argument('game_id', type=int)
    parser.add_argument('--download', '-d', help='Download game if not in database', action='store_true')


def main_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='hanabi_suite',
        description='High-level interface for analysis of hanabi instances.'
    )
    parser.add_argument('--verbose', '-v', help='Enable verbose logging to console', action='store_true')
    subparsers = parser.add_subparsers(dest='command', required=True, help='select subcommand')

    add_init_subparser(subparsers)
    add_analyze_subparser(subparsers)
    add_download_subparser(subparsers)

    return parser


def hanabi_cli():
    args = main_parser().parse_args()
    switcher = {
        'analyze': subcommand_analyze,
        'init': subcommand_init,
        'download': subcommand_download
    }
    if args.verbose:
        logger_manager.set_console_level(verboselogs.VERBOSE)
    method_args = dict(vars(args))
    method_args.pop('command')
    method_args.pop('verbose')
    switcher[args.command](**method_args)


if __name__ == "__main__":
    hanabi_cli()
