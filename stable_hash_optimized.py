#!/usr/bin/env python3
"""
Optimized Stable Hash Implementation
===================================

A high-performance, cross-platform stable hash function that:
- Works consistently across processes/machines regardless of PYTHONHASHSEED
- Handles deep nesting without recursion limits
- Supports extensible custom types
- Optimizes for speed and memory efficiency

Key Features:
- Non-recursive traversal using explicit stack
- Streaming hash computation to avoid large memory allocations  
- IEEE754 binary encoding for floats with special value normalization
- Sorted digest-based ordering for sets/dicts
- Prefix-free encoding with type tags and length prefixes
- Dual extensibility: registration + magic method protocol
"""

from __future__ import annotations
import struct
import sys
from hashlib import md5, blake2b
from math import isnan, isinf
from typing import Any, Callable, Dict, Union, Optional
from collections.abc import Mapping, Sequence, Set as AbstractSet

# Type tags (single byte) for unambiguous encoding
T_NONE = b"\x00"
T_BOOL = b"\x01" 
T_INT = b"\x02"
T_FLOAT = b"\x03"
T_STR = b"\x04"
T_BYTES = b"\x05"
T_LIST = b"\x10"
T_TUPLE = b"\x11"
T_SET = b"\x12"
T_FROZENSET = b"\x13"
T_DICT = b"\x14"
T_CUSTOM = b"\x20"

# Configuration
USE_BLAKE2B = True  # Blake2b is typically faster than MD5 in CPython
DIGEST_SIZE = 16

def _get_hasher():
    """Get the hash function - Blake2b preferred for performance"""
    if USE_BLAKE2B:
        return blake2b(digest_size=DIGEST_SIZE)
    else:
        return md5()

def _len_prefix(length: int) -> bytes:
    """Create length prefix in ASCII format for prefix-free encoding"""
    return f"{length}:".encode("ascii")

def _encode_int(value: int) -> bytes:
    """Encode integer as decimal ASCII (canonical form)"""
    return str(value).encode("ascii")

def _encode_float(value: float) -> bytes:
    """
    Encode float with IEEE754 binary + special value normalization
    This ensures cross-platform consistency and handles edge cases
    """
    if isnan(value):
        return b"nan"
    if isinf(value):
        return b"+inf" if value > 0 else b"-inf"
    if value == 0.0:
        value = 0.0  # Normalize -0.0 to 0.0
    return struct.pack(">d", value)  # Big-endian double

def _encode_str(value: str) -> bytes:
    """Encode string as UTF-8"""
    return value.encode("utf-8")

def _encode_bytes(value: Union[bytes, bytearray]) -> bytes:
    """Ensure bytes object"""
    return bytes(value)

# Extensibility: Type handler registry
Handler = Callable[[Any], bytes]
_REGISTRY: Dict[type, Handler] = {}

def register_type(type_class: type, handler: Handler) -> None:
    """
    Register a custom type handler
    
    Args:
        type_class: The type to handle
        handler: Function that converts instance to stable bytes representation
    
    Example:
        def point_handler(p):
            return struct.pack(">dd", p.x, p.y)
        register_type(Point, point_handler)
    """
    _REGISTRY[type_class] = handler

def unregister_type(type_class: type) -> None:
    """Remove a registered type handler"""
    _REGISTRY.pop(type_class, None)

# Stack states for non-recursive traversal
STATE_INITIAL = 0
STATE_AGGREGATE = 1

class StableHasher:
    """
    High-performance stable hash computer with non-recursive traversal
    """
    
    __slots__ = ('_digest_stack', '_work_stack')
    
    def __init__(self):
        self._digest_stack: list[bytes] = []
        self._work_stack: list[tuple[Any, int, Any]] = []
    
    def hash(self, obj: Any) -> bytes:
        """
        Compute stable hash digest for an object
        
        Returns:
            16-byte digest that's consistent across runs and platforms
        """
        self._digest_stack.clear()
        self._work_stack.clear()
        self._work_stack.append((obj, STATE_INITIAL, None))
        
        while self._work_stack:
            node, state, aux = self._work_stack.pop()
            
            if state == STATE_INITIAL:
                self._process_initial(node)
            else:  # STATE_AGGREGATE
                self._process_aggregate(node, aux)
        
        return self._digest_stack[0]
    
    def _process_initial(self, node: Any) -> None:
        """Process a node in initial state"""
        # None
        if node is None:
            self._push_digest(T_NONE)
            return
        
        # Check for magic method protocol
        if hasattr(node, '__stable_hash__'):
            try:
                digest = node.__stable_hash__()
                if not isinstance(digest, (bytes, bytearray)) or len(digest) != DIGEST_SIZE:
                    raise ValueError(f"__stable_hash__ must return {DIGEST_SIZE}-byte digest")
                self._digest_stack.append(bytes(digest))
                return
            except Exception as e:
                raise TypeError(f"Error in __stable_hash__ for {type(node)}: {e}")
        
        # Check registry
        node_type = type(node)
        for registered_type, handler in _REGISTRY.items():
            if isinstance(node, registered_type):
                try:
                    payload = handler(node)
                    if not isinstance(payload, (bytes, bytearray)):
                        raise ValueError("Handler must return bytes")
                    self._push_custom_digest(payload)
                    return
                except Exception as e:
                    raise TypeError(f"Error in registered handler for {registered_type}: {e}")
        
        # Built-in types
        if node_type is bool:
            self._push_digest(T_BOOL, b"1" if node else b"0")
        elif node_type is int:
            self._push_digest(T_INT, _encode_int(node))
        elif node_type is float:
            self._push_digest(T_FLOAT, _encode_float(node))
        elif node_type is str:
            encoded = _encode_str(node)
            self._push_digest(T_STR, _len_prefix(len(encoded)), encoded)
        elif node_type in (bytes, bytearray):
            encoded = _encode_bytes(node)
            self._push_digest(T_BYTES, _len_prefix(len(encoded)), encoded)
        elif isinstance(node, (list, tuple)):
            self._process_sequence(node)
        elif isinstance(node, (set, frozenset)):
            self._process_set(node)
        elif isinstance(node, dict):
            self._process_dict(node)
        else:
            raise TypeError(f"Unsupported type: {node_type.__name__}")
    
    def _process_sequence(self, seq: Union[list, tuple]) -> None:
        """Process list or tuple"""
        tag = T_LIST if isinstance(seq, list) else T_TUPLE
        length = len(seq)
        
        # Push aggregation task
        self._work_stack.append(((tag, length), STATE_AGGREGATE, None))
        
        # Push children in reverse order (stack processes in reverse)
        for item in reversed(seq):
            self._work_stack.append((item, STATE_INITIAL, None))
    
    def _process_set(self, s: Union[set, frozenset]) -> None:
        """Process set or frozenset"""
        tag = T_SET if isinstance(s, set) else T_FROZENSET
        items = list(s)
        length = len(items)
        
        # Push aggregation task
        self._work_stack.append(((tag, length), STATE_AGGREGATE, "sort_digests"))
        
        # Push all items
        for item in items:
            self._work_stack.append((item, STATE_INITIAL, None))
    
    def _process_dict(self, d: dict) -> None:
        """Process dictionary"""
        items = list(d.items())
        length = len(items)
        
        # Push aggregation task
        self._work_stack.append(((T_DICT, length), STATE_AGGREGATE, items))
        
        # Push key-value pairs in reverse order
        # Values first, then keys (so keys are processed first due to stack order)
        for key, value in reversed(items):
            self._work_stack.append((value, STATE_INITIAL, None))
            self._work_stack.append((key, STATE_INITIAL, None))
    
    def _process_aggregate(self, node_info: tuple, aux: Any) -> None:
        """Process aggregation of child digests"""
        tag, length = node_info
        
        if tag in (T_LIST, T_TUPLE):
            # Take last `length` digests and aggregate
            children = self._digest_stack[-length:] if length > 0 else []
            if length > 0:
                del self._digest_stack[-length:]
            
            hasher = _get_hasher()
            hasher.update(tag)
            hasher.update(_len_prefix(length))
            for digest in children:
                hasher.update(digest)
            self._digest_stack.append(hasher.digest())
        
        elif tag in (T_SET, T_FROZENSET):
            # Take last `length` digests, sort them, then aggregate
            children = self._digest_stack[-length:] if length > 0 else []
            if length > 0:
                del self._digest_stack[-length:]
            
            children.sort()  # Sort digests for deterministic order
            
            hasher = _get_hasher()
            hasher.update(tag)
            hasher.update(_len_prefix(length))
            for digest in children:
                hasher.update(digest)
            self._digest_stack.append(hasher.digest())
        
        elif tag is T_DICT:
            # Take last `2*length` digests, pair them, sort by key digest, aggregate
            total_digests = 2 * length
            children = self._digest_stack[-total_digests:] if total_digests > 0 else []
            if total_digests > 0:
                del self._digest_stack[-total_digests:]
            
            # Pair up as (key_digest, value_digest)
            pairs = []
            for i in range(0, len(children), 2):
                key_digest = children[i]
                value_digest = children[i + 1] if i + 1 < len(children) else b'\x00' * DIGEST_SIZE
                pairs.append((key_digest, value_digest))
            
            # Sort by key digest, then by value digest for tie-breaking
            pairs.sort(key=lambda kv: (kv[0], kv[1]))
            
            hasher = _get_hasher()
            hasher.update(T_DICT)
            hasher.update(_len_prefix(length))
            for key_digest, value_digest in pairs:
                hasher.update(key_digest)
                hasher.update(value_digest)
            self._digest_stack.append(hasher.digest())
        
        else:
            raise AssertionError(f"Unknown container tag: {tag}")
    
    def _push_digest(self, *parts: bytes) -> None:
        """Create digest from parts and push to stack"""
        hasher = _get_hasher()
        for part in parts:
            hasher.update(part)
        self._digest_stack.append(hasher.digest())
    
    def _push_custom_digest(self, payload: bytes) -> None:
        """Push digest for custom type"""
        hasher = _get_hasher()
        hasher.update(T_CUSTOM)
        hasher.update(_len_prefix(len(payload)))
        hasher.update(payload)
        self._digest_stack.append(hasher.digest())

# Singleton instance for convenience
_default_hasher = StableHasher()

def stable_hash(obj: Any) -> bytes:
    """
    Compute stable hash digest for an object
    
    Args:
        obj: Object to hash (supports None, bool, int, float, str, bytes, 
             list, tuple, set, frozenset, dict, and registered custom types)
    
    Returns:
        16-byte digest that's consistent across runs and platforms
    
    Raises:
        TypeError: For unsupported types
    """
    return _default_hasher.hash(obj)

def stable_hash_hex(obj: Any) -> str:
    """
    Compute stable hash digest as hex string
    
    Args:
        obj: Object to hash
    
    Returns:
        32-character hex string representation of the digest
    """
    return stable_hash(obj).hex()

def stable_hash_int(obj: Any) -> int:
    """
    Compute stable hash digest as integer
    
    Args:
        obj: Object to hash
    
    Returns:
        Integer representation of the digest
    """
    return int.from_bytes(stable_hash(obj), 'big')

# Convenience function for multiple objects
def stable_hash_many(*objects) -> bytes:
    """
    Compute stable hash for multiple objects as if they were in a tuple
    
    Args:
        *objects: Objects to hash together
    
    Returns:
        16-byte digest for the tuple of objects
    """
    return stable_hash(tuple(objects))

# Configuration utilities
def set_hash_algorithm(use_blake2b: bool = True) -> None:
    """
    Set the hash algorithm preference
    
    Args:
        use_blake2b: If True, use Blake2b (faster), if False use MD5
    """
    global USE_BLAKE2B
    USE_BLAKE2B = use_blake2b

def get_hash_algorithm() -> str:
    """Get current hash algorithm name"""
    return "blake2b" if USE_BLAKE2B else "md5"

# Performance utilities
class StableHashCache:
    """
    LRU cache for stable hash results to speed up repeated computations
    """
    
    def __init__(self, maxsize: int = 1024):
        self.maxsize = maxsize
        self.cache: Dict[int, bytes] = {}
        self.access_order: list[int] = []
    
    def get(self, obj: Any) -> Optional[bytes]:
        """Get cached hash if available"""
        try:
            # Use Python's built-in hash as cache key (fast but may have collisions)
            key = hash(obj)
            if key in self.cache:
                # Move to end (most recently used)
                self.access_order.remove(key)
                self.access_order.append(key)
                return self.cache[key]
        except TypeError:
            # Unhashable type, can't cache
            pass
        return None
    
    def put(self, obj: Any, digest: bytes) -> None:
        """Store hash in cache"""
        try:
            key = hash(obj)
            if key in self.cache:
                # Update existing
                self.access_order.remove(key)
            elif len(self.cache) >= self.maxsize:
                # Evict least recently used
                lru_key = self.access_order.pop(0)
                del self.cache[lru_key]
            
            self.cache[key] = digest
            self.access_order.append(key)
        except TypeError:
            # Unhashable type, can't cache
            pass
    
    def clear(self) -> None:
        """Clear the cache"""
        self.cache.clear()
        self.access_order.clear()

class CachedStableHasher(StableHasher):
    """Stable hasher with LRU caching for better performance on repeated objects"""
    
    def __init__(self, cache_size: int = 1024):
        super().__init__()
        self.cache = StableHashCache(cache_size)
    
    def hash(self, obj: Any) -> bytes:
        """Compute hash with caching"""
        # Try cache first
        cached = self.cache.get(obj)
        if cached is not None:
            return cached
        
        # Compute and cache
        digest = super().hash(obj)
        self.cache.put(obj, digest)
        return digest

# Example custom type implementations
def register_common_types():
    """Register handlers for some common types"""
    
    # Complex numbers
    def complex_handler(c: complex) -> bytes:
        return struct.pack(">dd", c.real, c.imag)
    
    # Decimal (if available)
    try:
        from decimal import Decimal
        def decimal_handler(d: Decimal) -> bytes:
            return str(d).encode('ascii')
        register_type(Decimal, decimal_handler)
    except ImportError:
        pass
    
    # UUID (if available)
    try:
        from uuid import UUID
        def uuid_handler(u: UUID) -> bytes:
            return u.bytes
        register_type(UUID, uuid_handler)
    except ImportError:
        pass
    
    register_type(complex, complex_handler)

if __name__ == "__main__":
    # Auto-register common types
    register_common_types()