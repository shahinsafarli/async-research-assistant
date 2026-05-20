"""
Async Research Assistant — SE layer package.
Configures structured logging on import.
"""
import logging
from src.config import settings


def setup_logging() -> None:
    """Configure structured logging from env var."""
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


setup_logging()
