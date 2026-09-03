import os
import time

# ULID-style sortable ID: 48-bit millisecond timestamp + 80-bit randomness
# Encoded as Crockford Base32 for compactness and sortability
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _encode_crockford(value: int, length: int) -> str:
    """Encode an integer as a Crockford Base32 string of fixed length."""
    result = []
    for _ in range(length):
        result.append(_CROCKFORD[value & 0x1F])
        value >>= 5
    return "".join(reversed(result))


def new_id(prefix: str) -> str:
    """Generate a lexicographically sortable unique ID (ULID-style).
    Format: {prefix}_{26-char Crockford Base32 ULID}
    """
    timestamp_ms = int(time.time() * 1000)
    randomness = int.from_bytes(os.urandom(10), "big")
    # 10 bytes = 80 bits → 16 Crockford chars; 48-bit timestamp → 10 chars
    ts_part = _encode_crockford(timestamp_ms, 10)
    rand_part = _encode_crockford(randomness, 16)
    return f"{prefix}_{ts_part}{rand_part}"
