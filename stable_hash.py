# stable_hash.py
from __future__ import annotations
from hashlib import md5
from math import isnan, isinf
import struct
from typing import Any, Callable, Dict

# ---- 类型标签（1 字节） ----
T_NONE   = b"\x00"
T_BOOL   = b"\x03"
T_INT    = b"\x01"
T_FLOAT  = b"\x06"
T_STR    = b"\x02"
T_BYTES  = b"\x04"
T_LIST   = b"\x10"
T_TUPLE  = b"\x11"
T_SET    = b"\x12"
T_DICT   = b"\x13"
T_CUSTOM = b"\x20"  # 自定义类型

def _len_bytes(n: int) -> bytes:
    return f"{n}:".encode("ascii")

def _int_bytes(i: int) -> bytes:
    return str(i).encode("ascii")

def _float_bytes(x: float) -> bytes:
    if isnan(x): return b"nan"
    if isinf(x): return b"+inf" if x > 0 else b"-inf"
    if x == 0.0: x = 0.0  # 折叠 -0.0
    return struct.pack(">d", x)

def _str_bytes(s: str) -> bytes:
    return s.encode("utf-8")

# ---- 可扩展注册表 ----
Handler = Callable[[Any], bytes]
_REGISTRY: Dict[type, Handler] = {}

def register(type_: type, handler: Handler):
    _REGISTRY[type_] = handler

# ---- 主函数：非递归 + 流式 ----
def stable_hash(obj: Any) -> bytes:
    md5_new = md5
    out_stack: list[bytes] = []
    stack: list[tuple[Any, int, Any]] = [(obj, 0, None)]  # (node, state, aux); state: 0 初始, 1 聚合

    while stack:
        node, state, aux = stack.pop()
        if state == 0:
            if node is None:
                out_stack.append(md5_new(T_NONE).digest()); continue

            proto = getattr(node, "__stable_hash__", None)
            if callable(proto):
                digest = node.__stable_hash__()
                if not (isinstance(digest, (bytes, bytearray)) and len(digest) == 16):
                    raise TypeError("__stable_hash__ must return 16-byte digest")
                out_stack.append(digest); continue

            for tp, handler in _REGISTRY.items():
                if isinstance(node, tp):
                    payload = handler(node)
                    out_stack.append(md5_new(T_CUSTOM + _len_bytes(len(payload)) + payload).digest())
                    break
            else:
                t = type(node)
                if t is bool:
                    out_stack.append(md5_new(T_BOOL + (b"1" if node else b"0")).digest())
                elif t is int:
                    out_stack.append(md5_new(T_INT + _int_bytes(node)).digest())
                elif t is float:
                    out_stack.append(md5_new(T_FLOAT + _float_bytes(node)).digest())
                elif t is str:
                    b = _str_bytes(node); out_stack.append(md5_new(T_STR + _len_bytes(len(b)) + b).digest())
                elif t is bytes or t is bytearray:
                    b = bytes(node); out_stack.append(md5_new(T_BYTES + _len_bytes(len(b)) + b).digest())
                elif isinstance(node, (list, tuple)):
                    tag = T_LIST if isinstance(node, list) else T_TUPLE
                    stack.append(((tag, len(node)), 1, None))
                    for item in reversed(node):
                        stack.append((item, 0, None))
                elif isinstance(node, (set, frozenset)):
                    items = list(node)
                    stack.append(((T_SET, len(items)), 1, "collect_sorted"))
                    for item in items:
                        stack.append((item, 0, None))
                elif isinstance(node, dict):
                    items = list(node.items())
                    stack.append(((T_DICT, len(items)), 1, items))
                    for k, v in reversed(items):
                        stack.append((v, 0, None)); stack.append((k, 0, None))
                else:
                    raise TypeError(f"Unsupported type: {t!r}")
        else:
            tag, length = node
            if tag in (T_LIST, T_TUPLE):
                children = out_stack[-length:] if length else ()
                if length: del out_stack[-length:]
                h = md5_new(); h.update(tag); h.update(_len_bytes(length))
                for d in children: h.update(d)
                out_stack.append(h.digest())
            elif tag is T_SET:
                children = out_stack[-length:] if length else ()
                if length: del out_stack[-length:]
                children = sorted(children)
                h = md5_new(); h.update(T_SET); h.update(_len_bytes(length))
                for d in children: h.update(d)
                out_stack.append(h.digest())
            elif tag is T_DICT:
                chunk = out_stack[-2*length:] if length else ()
                if length: del out_stack[-2*length:]
                pairs = [(chunk[i], chunk[i+1]) for i in range(0, len(chunk), 2)]
                pairs.sort(key=lambda kv: (kv[0], kv[1]))
                h = md5_new(); h.update(T_DICT); h.update(_len_bytes(length))
                for kd, vd in pairs: h.update(kd); h.update(vd)
                out_stack.append(h.digest())
            else:
                raise AssertionError("unknown container tag")

    return out_stack[0]

def stable_hash_hex(obj: Any) -> str:
    return stable_hash(obj).hex()