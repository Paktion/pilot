"""Logger configuration."""

from __future__ import annotations

import logging


def setup_logging(verbose: bool = False) -> logging.Logger:
    """Configure the ``pilotd`` root logger."""
    logger = logging.getLogger("pilotd")
    level = logging.DEBUG if verbose else logging.INFO

    if logger.handlers:
        logger.setLevel(level)
        return logger

    logger.setLevel(level)
    handler = logging.StreamHandler()
    handler.setLevel(level)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(handler)
    return logger
