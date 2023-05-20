from .logger_setup import LoggerManager

logger_manager = LoggerManager()
logger = logger_manager.get_logger()
