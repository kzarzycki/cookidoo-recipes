from __future__ import annotations

import socket
import ssl

import certifi
from aiohttp import TCPConnector


def cookidoo_connector() -> TCPConnector:
    context = ssl.create_default_context(cafile=certifi.where())
    return TCPConnector(family=socket.AF_INET, ssl=context)
