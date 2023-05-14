import logging


logger = logging.getLogger("HANAB")

logger.setLevel(logging.DEBUG)

handler = logging.FileHandler("log.txt")

logger.addHandler(handler)
