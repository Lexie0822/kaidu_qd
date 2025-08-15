"""
Stable Hash Implementation for Cross-Process Consistency

A production-ready implementation that provides stable, deterministic hashing
for Python objects across different processes and machines, independent of
PYTHONHASHSEED.

Key Features:
- Non-recursive traversal (no recursion depth limits)
- Streaming aggregation (memory efficient)
- Extensible type system
- Cross-platform IEEE754 float handling
- Prefix-free encoding to avoid ambiguity
"""

from __future__ import annotations
import struct
from hashlib import md5
from math import isnan, isinf
from typing import Any, Callable, Dict, Union

# Type tags for unambiguous encoding
_TYPE_NONE = b'\x00'
_TYPE_BOOL = b'\x01' 
_TYPE_INT = b'\x02'
_TYPE_FLOAT = b'\x03'
_TYPE_STR = b'\x04'
_TYPE_BYTES = b'\x05'
_TYPE_LIST = b'\x10'
_TYPE_TUPLE = b'\x11'
_TYPE_SET = b'\x12'
_TYPE_DICT = b'\x13'
_TYPE_CUSTOM = b'\x20'

# Extension registry
_TypeHandler = Callable[[Any], bytes]
_type_registry: Dict[type, _TypeHandler] = {}

def register_type_handler(type_class: type, handler: _TypeHandler) -> None:
    """Register a custom type handler for extensibility.
    
    Args:
        type_class: The type to handle
        handler: Function that converts instance to stable bytes representation
    """
    _type_registry[type_class] = handler

def _encode_length(length: int) -> bytes:
    """Encode length as ASCII decimal followed by colon for prefix-free property."""
    return f"{length}:".encode('ascii')

def _normalize_float(value: float) -> bytes:
    """Convert float to normalized binary representation."""
    if isnan(value):
        return b'nan'
    if isinf(value):
        return b'+inf' if value > 0 else b'-inf'
    # Normalize -0.0 to 0.0 for consistency
    if value == 0.0:
        value = 0.0
    return struct.pack('>d', value)

def _encode_atomic_value(obj: Any) -> bytes:
    """Encode atomic (non-container) values with type tags."""
    obj_type = type(obj)
    
    if obj is None:
        return _TYPE_NONE
    
    # Check for custom __stable_hash__ method first
    if hasattr(obj, '__stable_hash__') and callable(obj.__stable_hash__):
        digest = obj.__stable_hash__()
        if not isinstance(digest, (bytes, bytearray)) or len(digest) != 16:
            raise ValueError("__stable_hash__ must return exactly 16 bytes")
        return digest
    
    # Check registered handlers
    for registered_type, handler in _type_registry.items():
        if isinstance(obj, registered_type):
            payload = handler(obj)
            return _TYPE_CUSTOM + _encode_length(len(payload)) + payload
    
    # Built-in type handling
    if obj_type is bool:
        return _TYPE_BOOL + (b'1' if obj else b'0')
    elif obj_type is int:
        return _TYPE_INT + str(obj).encode('ascii')
    elif obj_type is float:
        return _TYPE_FLOAT + _normalize_float(obj)
    elif obj_type is str:
        utf8_bytes = obj.encode('utf-8')
        return _TYPE_STR + _encode_length(len(utf8_bytes)) + utf8_bytes
    elif obj_type in (bytes, bytearray):
        data = bytes(obj)
        return _TYPE_BYTES + _encode_length(len(data)) + data
    else:
        raise TypeError(f"Unsupported atomic type: {obj_type}")

def stable_hash(obj: Any) -> bytes:
    """
    Compute a stable 16-byte hash digest for any supported Python object.
    
    The hash is deterministic across different Python processes and machines,
    independent of PYTHONHASHSEED. Uses non-recursive traversal to handle
    arbitrary nesting depth.
    
    Args:
        obj: Object to hash
        
    Returns:
        16-byte MD5 digest
        
    Raises:
        TypeError: For unsupported types
        ValueError: For malformed __stable_hash__ return values
    """
    # Stack for non-recursive traversal: (object, phase, metadata)
    # phase 0: initial processing, phase 1: aggregation
    work_stack = [(obj, 0, None)]
    digest_stack = []
    
    while work_stack:
        current_obj, phase, metadata = work_stack.pop()
        
        if phase == 0:  # Initial processing phase
            obj_type = type(current_obj)
            
            # Handle containers that need child processing
            if obj_type in (list, tuple):
                tag = _TYPE_LIST if obj_type is list else _TYPE_TUPLE
                length = len(current_obj)
                
                # Push aggregation phase
                work_stack.append(((tag, length), 1, None))
                # Push children in reverse order for correct processing
                for item in reversed(current_obj):
                    work_stack.append((item, 0, None))
                    
            elif obj_type in (set, frozenset):
                items = list(current_obj)
                length = len(items)
                
                # Push aggregation phase  
                work_stack.append(((_TYPE_SET, length), 1, 'sort_children'))
                # Push all items
                for item in items:
                    work_stack.append((item, 0, None))
                    
            elif obj_type is dict:
                items = list(current_obj.items())
                length = len(items)
                
                # Push aggregation phase
                work_stack.append(((_TYPE_DICT, length), 1, None))
                # Push key-value pairs in reverse order
                for key, value in reversed(items):
                    work_stack.append((value, 0, None))
                    work_stack.append((key, 0, None))
                    
            else:
                # Atomic value - compute digest immediately
                encoded = _encode_atomic_value(current_obj)
                digest_stack.append(md5(encoded).digest())
                
        else:  # Aggregation phase
            tag, length = current_obj
            
            # Collect child digests
            if tag == _TYPE_DICT:
                # Dictionary has 2 * length children (key-value pairs)
                children_count = length * 2
            else:
                children_count = length
                
            if children_count > 0:
                children = digest_stack[-children_count:]
                del digest_stack[-children_count:]
            else:
                children = []
            
            # Create hasher for this container
            hasher = md5()
            hasher.update(tag)
            hasher.update(_encode_length(length))
            
            if tag == _TYPE_SET and metadata == 'sort_children':
                # Sort digests for deterministic set/frozenset handling
                children.sort()
            elif tag == _TYPE_DICT:
                # Group and sort key-value pairs
                pairs = [(children[i], children[i + 1]) for i in range(0, len(children), 2)]
                pairs.sort(key=lambda kv: (kv[0], kv[1]))  # Sort by key digest, then value digest
                children = [digest for pair in pairs for digest in pair]
            
            # Stream all child digests
            for child_digest in children:
                hasher.update(child_digest)
                
            digest_stack.append(hasher.digest())
    
    return digest_stack[0]

def stable_hash_hex(obj: Any) -> str:
    """Convenience function returning hex representation of stable hash."""
    return stable_hash(obj).hex()

# Example custom type registration
class Point:
    """Example custom type with stable hash support."""
    
    def __init__(self, x: float, y: float):
        self.x = float(x)
        self.y = float(y)
    
    def __stable_hash__(self) -> bytes:
        """Custom stable hash implementation."""
        hasher = md5()
        hasher.update(b'Point:')
        hasher.update(struct.pack('>d', self.x))
        hasher.update(struct.pack('>d', self.y))
        return hasher.digest()

# Alternative registration approach for Point
def _point_handler(point: Point) -> bytes:
    """Handler function for Point type."""
    return b'Point:' + struct.pack('>dd', point.x, point.y)

# Uncomment to use handler-based registration instead:
# register_type_handler(Point, _point_handler)