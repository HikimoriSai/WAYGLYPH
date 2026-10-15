"""Input limits shared by graph uploads and API routes."""
import math
import re

MAX_NODES = 1000
MAX_EDGES = 10000


def node_id(value):
    if not isinstance(value, str):
        raise ValueError('Node ID must be text.')
    value = value.strip().upper()
    if not re.fullmatch(r'[A-Z][A-Z0-9]{0,15}', value):
        raise ValueError('Node IDs must be 1–16 letters or digits, starting with a letter.')
    return value


def coordinate(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError('Coordinates must be finite numbers.')
    if not math.isfinite(value) or abs(value) > 1_000_000:
        raise ValueError('Coordinates must be finite and within ±1,000,000.')
    return float(value)


def weight(value):
    if not math.isfinite(value) or not 0 <= value <= 10_000_000:
        raise ValueError('Edge weights must be finite numbers from 0 to 10,000,000.')
    return value


def cipher_key(value):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 25:
        raise ValueError('Cipher key must be an integer from 0 to 25.')
    return value
