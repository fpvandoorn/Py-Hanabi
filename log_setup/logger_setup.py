import logging
import verboselogs


class LoggerManager:
    def __init__(self, console_level: int = logging.INFO):
        self.logger = verboselogs.VerboseLogger("hanab-suite")

        self.logger.setLevel(logging.DEBUG)

        self.file_formatter = logging.Formatter(
            '[%(asctime)s] [PID %(process)s] [%(levelname)7s]: %(message)s'
        )

        self.info_file_formatter = logging.Formatter(
            '[%(asctime)s] [PID %(process)s]: %(message)s'
        )

        self.console_formatter = logging.Formatter(
            '[%(levelname)7s]: %(message)s'
        )

        self.nothing_formatter = logging.Formatter(
            '%(message)s'
        )


        self.console_handler = logging.StreamHandler()
        self.console_handler.setLevel(console_level)
        self.console_handler.setFormatter(self.nothing_formatter)

        self.debug_file_handler = logging.FileHandler("debug_log.txt")
        self.debug_file_handler.setFormatter(self.file_formatter)
        self.debug_file_handler.setLevel(logging.DEBUG)

        self.verbose_file_handler = logging.FileHandler("verbose_log.txt")
        self.verbose_file_handler.setFormatter(self.file_formatter)
        self.verbose_file_handler.setLevel(verboselogs.VERBOSE)

        self.info_file_handler = logging.FileHandler("log.txt")
        self.info_file_handler.setFormatter(self.info_file_formatter)
        self.info_file_handler.setLevel(logging.INFO)

        self.logger.addHandler(self.console_handler)
        self.logger.addHandler(self.debug_file_handler)
        self.logger.addHandler(self.verbose_file_handler)
        self.logger.addHandler(self.info_file_handler)

    def set_console_level(self, level: int):
        self.console_handler.setLevel(level)
        if level == logging.INFO:
            self.console_handler.setFormatter(self.nothing_formatter)
        else:
            self.console_handler.setFormatter(self.console_formatter)

    def is_console_level_active(self, level: int):
        return level >= self.console_handler.level

    def get_logger(self):
        return self.logger
