#!/usr/bin/env python3
"""
Original Stable Hash Implementation (from Chinese specification)
================================================================

This is the baseline implementation that was provided in the Chinese text
for comparison purposes. It has the issues mentioned:
1. Performance problems (string concatenation, recursive calls)
2. Recursion depth limitations  
3. Limited extensibility
"""

from hashlib import md5
from typing import Any

def md5_hash(data: bytes) -> bytes:
    return md5(data).digest()

def my_hash(obj: Any) -> bytes:
    if isinstance(obj, str):
        return md5_hash(b"\x02" + obj.encode())
    elif isinstance(obj, (int, float)):
        return md5_hash(b"\x01" + str(obj).encode())
    elif obj is None:
        return md5_hash(b"\x00")
    elif isinstance(obj, list):
        return md5_hash(
            b"list" + b",".join(my_hash(item) for item in obj)
        )
    elif isinstance(obj, dict):
        # Note: This has the ordering issue mentioned in the spec
        return md5_hash(
            b"dict" + 
            b",".join(my_hash(k) + my_hash(v) for k, v in obj.items())
        )
    # tuple / set could be handled similarly, but left incomplete
    else:
        raise TypeError(f"Unsupported type: {type(obj)}")

def stable_hash_original(obj: Any) -> bytes:
    """Original implementation with all the mentioned problems"""
    return my_hash(obj)

def stable_hash_hex_original(obj: Any) -> str:
    """Original implementation returning hex string"""
    return stable_hash_original(obj).hex()