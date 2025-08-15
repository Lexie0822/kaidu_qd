#!/usr/bin/env python3
"""
稳定对象哈希实现 - 优化版

解决原始my_hash的三个关键问题：
1. 性能瓶颈：大量字符串拼接，递归调用开销
2. 递归深度限制：默认1000层限制在生产环境不够用  
3. 扩展性差：无法处理自定义类型

优化策略：
- 非递归后序遍历，支持任意深度
- 流式哈希计算，避免大内存分配
- IEEE754浮点编码，确保跨平台一致性
- 双扩展机制：注册表+魔术方法
"""

from __future__ import annotations
from hashlib import md5
from math import isnan, isinf
import struct
from typing import Any, Callable, Dict

# 类型标签 - 1字节前缀，确保类型不混淆
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
T_CUSTOM = b"\x20"

def _len_prefix(n: int) -> bytes:
    """长度前缀编码：ASCII数字+冒号，如 '5:' """
    return f"{n}:".encode("ascii")

def _encode_int(value: int) -> bytes:
    """整数编码：十进制ASCII，无前导零"""
    return str(value).encode("ascii")

def _encode_float(value: float) -> bytes:
    """
    浮点数编码：IEEE754二进制 + 特殊值处理
    关键：-0.0统一为0.0，避免符号位差异
    """
    if isnan(value):
        return b"nan"
    if isinf(value):
        return b"+inf" if value > 0 else b"-inf"
    if value == 0.0:
        value = 0.0  # 统一-0.0为0.0
    return struct.pack(">d", value)

def _encode_str(value: str) -> bytes:
    """字符串UTF-8编码"""
    return value.encode("utf-8")

# 自定义类型扩展机制
Handler = Callable[[Any], bytes]
_TYPE_REGISTRY: Dict[type, Handler] = {}

def register_type(type_class: type, handler: Handler) -> None:
    """
    注册自定义类型处理器
    
    Args:
        type_class: 要处理的类型
        handler: 转换函数，返回稳定的字节表示
    
    Example:
        def point_handler(p):
            return struct.pack(">dd", p.x, p.y)
        register_type(Point, point_handler)
    """
    _TYPE_REGISTRY[type_class] = handler

def stable_hash(obj: Any) -> bytes:
    """
    计算对象的稳定哈希摘要
    
    使用非递归后序遍历，支持任意深度嵌套
    返回16字节MD5摘要，保证跨平台跨进程一致性
    
    Args:
        obj: 要哈希的对象
        
    Returns:
        16字节摘要
        
    Raises:
        TypeError: 不支持的类型
    """
    digest_stack: list[bytes] = []
    work_stack: list[tuple[Any, int, Any]] = [(obj, 0, None)]
    
    while work_stack:
        node, state, aux = work_stack.pop()
        
        if state == 0:  # 初始状态：分解对象
            if node is None:
                digest_stack.append(md5(T_NONE).digest())
                continue
            
            # 优先检查魔术方法
            stable_hash_method = getattr(node, "__stable_hash__", None)
            if callable(stable_hash_method):
                digest = stable_hash_method()
                if not (isinstance(digest, (bytes, bytearray)) and len(digest) == 16):
                    raise TypeError("__stable_hash__ must return exactly 16 bytes")
                digest_stack.append(bytes(digest))
                continue
            
            # 检查类型注册表
            node_type = type(node)
            for registered_type, handler in _TYPE_REGISTRY.items():
                if isinstance(node, registered_type):
                    payload = handler(node)
                    if not isinstance(payload, (bytes, bytearray)):
                        raise TypeError("Type handler must return bytes")
                    digest_stack.append(md5(T_CUSTOM + _len_prefix(len(payload)) + payload).digest())
                    break
            else:
                # 内置类型处理
                if node_type is bool:
                    digest_stack.append(md5(T_BOOL + (b"1" if node else b"0")).digest())
                elif node_type is int:
                    digest_stack.append(md5(T_INT + _encode_int(node)).digest())
                elif node_type is float:
                    digest_stack.append(md5(T_FLOAT + _encode_float(node)).digest())
                elif node_type is str:
                    encoded = _encode_str(node)
                    digest_stack.append(md5(T_STR + _len_prefix(len(encoded)) + encoded).digest())
                elif node_type in (bytes, bytearray):
                    data = bytes(node)
                    digest_stack.append(md5(T_BYTES + _len_prefix(len(data)) + data).digest())
                elif isinstance(node, (list, tuple)):
                    tag = T_LIST if isinstance(node, list) else T_TUPLE
                    work_stack.append(((tag, len(node)), 1, None))
                    # 反向推入子元素（栈后进先出）
                    for item in reversed(node):
                        work_stack.append((item, 0, None))
                elif isinstance(node, (set, frozenset)):
                    items = list(node)
                    work_stack.append(((T_SET, len(items)), 1, "sort_needed"))
                    for item in items:
                        work_stack.append((item, 0, None))
                elif isinstance(node, dict):
                    items = list(node.items())
                    work_stack.append(((T_DICT, len(items)), 1, None))
                    # 键值对反向推入
                    for key, value in reversed(items):
                        work_stack.append((value, 0, None))
                        work_stack.append((key, 0, None))
                else:
                    raise TypeError(f"Unsupported type: {node_type.__name__}")
        
        else:  # state == 1：聚合状态
            tag, length = node
            
            if tag in (T_LIST, T_TUPLE):
                # 取出子元素摘要，流式计算
                children = digest_stack[-length:] if length > 0 else []
                if length > 0:
                    del digest_stack[-length:]
                
                hasher = md5()
                hasher.update(tag)
                hasher.update(_len_prefix(length))
                for child_digest in children:
                    hasher.update(child_digest)
                digest_stack.append(hasher.digest())
            
            elif tag == T_SET:
                # 集合需要排序确保稳定性
                children = digest_stack[-length:] if length > 0 else []
                if length > 0:
                    del digest_stack[-length:]
                
                children.sort()  # 对摘要字节排序
                
                hasher = md5()
                hasher.update(T_SET)
                hasher.update(_len_prefix(length))
                for child_digest in children:
                    hasher.update(child_digest)
                digest_stack.append(hasher.digest())
            
            elif tag == T_DICT:
                # 字典按键摘要排序
                total_digests = 2 * length
                children = digest_stack[-total_digests:] if total_digests > 0 else []
                if total_digests > 0:
                    del digest_stack[-total_digests:]
                
                # 配对键值摘要
                pairs = []
                for i in range(0, len(children), 2):
                    key_digest = children[i]
                    value_digest = children[i + 1] if i + 1 < len(children) else b'\x00' * 16
                    pairs.append((key_digest, value_digest))
                
                # 按键摘要排序，值摘要作为次要排序键
                pairs.sort(key=lambda pair: (pair[0], pair[1]))
                
                hasher = md5()
                hasher.update(T_DICT)
                hasher.update(_len_prefix(length))
                for key_digest, value_digest in pairs:
                    hasher.update(key_digest)
                    hasher.update(value_digest)
                digest_stack.append(hasher.digest())
            
            else:
                raise AssertionError(f"Unknown container tag: {tag}")
    
    return digest_stack[0]

def stable_hash_hex(obj: Any) -> str:
    """返回稳定哈希的十六进制字符串表示"""
    return stable_hash(obj).hex()

# 便利函数
def hash_many(*objects) -> bytes:
    """计算多个对象的联合哈希，等价于hash(tuple(objects))"""
    return stable_hash(tuple(objects))

if __name__ == "__main__":
    # 原始测试用例
    def f():
        va = {"float": [1.0, 2.0, 3.0, None, 4.0, None, 5.0] * 10}
        vb = {"int": [1, 2, 3, None, 4, None, 5] * 10}
        vc = {"str": ["1", "9", "2", "3", "None"] * 10 + ["4", "None", "5"] * 10}
        vd = {"left": va, "right": vb}
        ve = {"left": vc, "right": vd}
        f_ = {"single": ve}
        return f_
    
    result = stable_hash_hex(f())
    print(f"稳定哈希结果: {result}")
    
    # 验证一致性
    result2 = stable_hash_hex(f())
    assert result == result2, "哈希不一致"
    print("一致性验证通过")