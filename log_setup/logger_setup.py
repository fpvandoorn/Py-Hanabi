import logging


def make_logger():
    logger = logging.getLogger("hanab-suite")

    logger.setLevel(logging.DEBUG)

    f_handler = logging.FileHandler("a_log.txt")
    f_formatter = logging.Formatter(
        '[%(asctime)s] [%(name)s] [%(levelname)s]: %(message)s'
    )
    f_handler.setFormatter(f_formatter)
    logger.addHandler(f_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    logger.addHandler(console_handler)

    return logger
