from .database import DBConnectionManager

global_db_connection_manager = DBConnectionManager()

conn = global_db_connection_manager.lazy_conn
cur = global_db_connection_manager.lazy_cur
