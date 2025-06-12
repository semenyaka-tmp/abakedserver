from typing import Any
from .logging import configure_logger

logger = configure_logger('abakedserver')

def check_that(arg: Any, req: str, msg: str) -> None:
    """
    Validate an argument against a specified requirement.

    Args:
        arg: The argument to validate.
        req: The requirement string (e.g., 'is number', 'is positive', 'is bool').
        msg: The error message to log and raise if validation fails.

    Raises:
        ValueError: If the argument does not meet the requirement.
    """
    requirements = {
        'is number': lambda x: isinstance(x, (int, float)),
        'is non-negative': lambda x: isinstance(x, (int, float)) and x >= 0,
        'is positive': lambda x: isinstance(x, (int, float)) and x > 0,
        'is bool': lambda x: isinstance(x, bool),
        'is string': lambda x: isinstance(x, str),
        'is not empty string': lambda x: isinstance(x, str) and len(x.strip()) > 0,
        'is dict or none': lambda x: x is None or isinstance(x, dict),
        'is string or none': lambda x: x is None or isinstance(x, str),
        'is int': lambda x: isinstance(x, int),
        'is int or none': lambda x: x is None or isinstance(x, int),
    }

    if req not in requirements:
        logger.error(f"Unknown requirement: {req}")
        raise ValueError(f"Unknown requirement: {req}")

    if not requirements[req](arg):
        logger.error(msg)
        raise ValueError(msg)

