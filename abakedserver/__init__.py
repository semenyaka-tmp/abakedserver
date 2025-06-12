from .abaked_server import aBakedServer
from .stream_wrappers import WrappedSSHReader, WrappedSSHWriter
from .utils import check_that

"""
aBakedServer: TCP-based server with optional SSH tunnel under the hood
"""

import importlib.metadata

_metadata = importlib.metadata.metadata("abakedserver")
__version__ = _metadata["Version"]
__author__ = _metadata["Author-email"]
__license__ = _metadata["License"]

__all__ = [
    "aBakedServer",
    "WrappedSSHReader",
    "WrappedSSHWriter",
    "check_that",
]
