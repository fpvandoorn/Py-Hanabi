from typing import Optional
from pathlib import Path
import yaml

import psycopg2
import platformdirs

from hanabi import constants
from hanabi import logger


class LazyDBCursor:
    def __init__(self):
        self.__cur: Optional[psycopg2.cursor] = None

    def __getattr__(self, item):
        if self.__cur is None:
            raise ValueError(
                "DB cursor used in uninitialized state. Did you forget to initialize the DB connection?"
            )
        return getattr(self.__cur, item)

    def set_cur(self, cur):
        self.__cur = cur


class LazyDBConnection:
    def __init__(self):
        self.__conn: Optional[psycopg2.connection] = None

    def __getattr__(self, item):
        if self.__conn is None:
            raise ValueError(
                "DB connection used in uninitialized state. Did you forget to initialize the DB connection?"
            )
        return getattr(self.__conn, item)

    def set_conn(self, conn):
        self.__conn = conn


class DBConnectionManager:
    def __init__(self):
        self.lazy_conn: LazyDBConnection = LazyDBConnection()
        self.lazy_cur: LazyDBCursor = LazyDBCursor()
        self.config_file = Path(platformdirs.user_config_dir(constants.APP_NAME, ensure_exists=True)) / 'config.yaml'
        self.db_name: str = constants.DEFAULT_DB_NAME
        self.db_user: str = constants.DEFAULT_DB_USER
        self.db_pass: Optional[str] = None

    def read_config(self):
        logger.debug("DB connection configuration read from {}".format(self.config_file))
        if self.config_file.exists():
            with open(self.config_file, "r") as f:
                config = yaml.safe_load(f)
            self.db_name = config.get('dbname', None)
            self.db_user = config.get('dbuser', None)
            self.db_pass = config.get('dbpass', None)
            if self.db_name is None:
                logger.verbose("Falling back to default database name {}".format(constants.DEFAULT_DB_NAME))
                self.db_name = constants.DEFAULT_DB_NAME
            if self.db_user is None:
                logger.verbose("Falling back to default database user {}".format(constants.DEFAULT_DB_USER))
                self.db_user = constants.DEFAULT_DB_USER
        else:
            logger.info(
                "No configuration file for database connection found, falling back to default values "
                "(dbname={}, dbuser={}).".format(
                    constants.DEFAULT_DB_NAME, constants.DEFAULT_DB_USER
                )
            )
            logger.info(
                "Note: To turn off this message, create a config file at {}".format(self.config_file)
            )

    def create_config_file(self):
        if self.config_file.exists():
            raise FileExistsError("Configuration file already exists, not overriding.")
        self.config_file.write_text(
            "dbname: {}\n"
            "dbuser: {}\n"
            "dbpass: null".format(
                constants.DEFAULT_DB_NAME,
                constants.DEFAULT_DB_USER
            )
        )
        logger.info("Initialised default config file {}".format(self.config_file))

    def connect(self):
        conn = psycopg2.connect("dbname={} user={} password={}".format(self.db_name, self.db_user, self.db_pass))
        cur = conn.cursor()
        self.lazy_conn.set_conn(conn)
        self.lazy_cur.set_cur(cur)
