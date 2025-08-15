#!/usr/bin/env python3
"""
优化版稳定对象哈希实现
====================

高性能、跨平台一致的稳定对象哈希函数，解决以下问题：
- 跨进程/跨机器的哈希一致性，不受 PYTHONHASHSEED 影响
- 深度嵌套时不受递归深度限制
- 支持可扩展的自定义类型
- 优化速度和内存效率

核心特性：
- 非递归遍历，使用显式栈
- 流式哈希计算，避免大内存分配
- IEEE754标准浮点编码，处理特殊值归一化
- 基于摘要排序的集合/字典稳定排序
- 前缀无歧义编码，使用类型标签和长度前缀
- 双扩展协议：注册表 + 魔术方法
"""

from __future__ import annotations
import struct
import sys
from hashlib import md5, blake2b
from math import isnan, isinf
from typing import Any, Callable, Dict, Union, Optional
from collections.abc import Mapping, Sequence, Set as AbstractSet

# 类型标签（单字节），用于无歧义编码
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

# 配置选项
USE_BLAKE2B = True  # Blake2b 在 CPython 中通常比 MD5 更快
DIGEST_SIZE = 16

def _get_hasher():
    """获取哈希函数 - 优先使用 Blake2b 以获得更好性能"""
    if USE_BLAKE2B:
        return blake2b(digest_size=DIGEST_SIZE)
    else:
        return md5()

def _len_prefix(length: int) -> bytes:
    """创建 ASCII 格式的长度前缀，用于前缀无歧义编码"""
    return f"{length}:".encode("ascii")

def _encode_int(value: int) -> bytes:
    """将整数编码为十进制 ASCII（标准形式）"""
    return str(value).encode("ascii")

def _encode_float(value: float) -> bytes:
    """
    使用 IEEE754 二进制编码浮点数，并进行特殊值归一化
    确保跨平台一致性并处理边界情况
    """
    if isnan(value):
        return b"nan"
    if isinf(value):
        return b"+inf" if value > 0 else b"-inf"
    if value == 0.0:
        value = 0.0  # 将 -0.0 归一化为 0.0
    return struct.pack(">d", value)  # 大端序双精度

def _encode_str(value: str) -> bytes:
    """将字符串编码为 UTF-8"""
    return value.encode("utf-8")

def _encode_bytes(value: Union[bytes, bytearray]) -> bytes:
    """确保返回 bytes 对象"""
    return bytes(value)

# 可扩展性：类型处理器注册表
Handler = Callable[[Any], bytes]
_REGISTRY: Dict[type, Handler] = {}

def register_type(type_class: type, handler: Handler) -> None:
    """
    注册自定义类型处理器
    
    参数:
        type_class: 要处理的类型
        handler: 将实例转换为稳定字节表示的函数
    
    示例:
        def point_handler(p):
            return struct.pack(">dd", p.x, p.y)
        register_type(Point, point_handler)
    """
    _REGISTRY[type_class] = handler

def unregister_type(type_class: type) -> None:
    """移除已注册的类型处理器"""
    _REGISTRY.pop(type_class, None)

# 非递归遍历的栈状态
STATE_INITIAL = 0    # 初始状态
STATE_AGGREGATE = 1  # 聚合状态

class StableHasher:
    """
    高性能稳定哈希计算器，使用非递归遍历
    """
    
    __slots__ = ('_digest_stack', '_work_stack')
    
    def __init__(self):
        self._digest_stack: list[bytes] = []  # 摘要栈
        self._work_stack: list[tuple[Any, int, Any]] = []  # 工作栈
    
    def hash(self, obj: Any) -> bytes:
        """
        计算对象的稳定哈希摘要
        
        返回:
            16字节摘要，跨运行和平台保持一致
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
        """处理初始状态的节点"""
        # 处理 None
        if node is None:
            self._push_digest(T_NONE)
            return
        
        # 检查魔术方法协议
        if hasattr(node, '__stable_hash__'):
            try:
                digest = node.__stable_hash__()
                if not isinstance(digest, (bytes, bytearray)) or len(digest) != DIGEST_SIZE:
                    raise ValueError(f"__stable_hash__ 必须返回 {DIGEST_SIZE} 字节的摘要")
                self._digest_stack.append(bytes(digest))
                return
            except Exception as e:
                raise TypeError(f"{type(node)} 的 __stable_hash__ 出错: {e}")
        
        # 检查注册表
        node_type = type(node)
        for registered_type, handler in _REGISTRY.items():
            if isinstance(node, registered_type):
                try:
                    payload = handler(node)
                    if not isinstance(payload, (bytes, bytearray)):
                        raise ValueError("处理器必须返回 bytes")
                    self._push_custom_digest(payload)
                    return
                except Exception as e:
                    raise TypeError(f"{registered_type} 的注册处理器出错: {e}")
        
        # 内置类型处理
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
            raise TypeError(f"不支持的类型: {node_type.__name__}")
    
    def _process_sequence(self, seq: Union[list, tuple]) -> None:
        """处理列表或元组"""
        tag = T_LIST if isinstance(seq, list) else T_TUPLE
        length = len(seq)
        
        # 推入聚合任务
        self._work_stack.append(((tag, length), STATE_AGGREGATE, None))
        
        # 反向推入子元素（栈是后进先出）
        for item in reversed(seq):
            self._work_stack.append((item, STATE_INITIAL, None))
    
    def _process_set(self, s: Union[set, frozenset]) -> None:
        """处理集合或冻结集合"""
        tag = T_SET if isinstance(s, set) else T_FROZENSET
        items = list(s)
        length = len(items)
        
        # 推入聚合任务
        self._work_stack.append(((tag, length), STATE_AGGREGATE, "sort_digests"))
        
        # 推入所有元素
        for item in items:
            self._work_stack.append((item, STATE_INITIAL, None))
    
    def _process_dict(self, d: dict) -> None:
        """处理字典"""
        items = list(d.items())
        length = len(items)
        
        # 推入聚合任务
        self._work_stack.append(((T_DICT, length), STATE_AGGREGATE, items))
        
        # 反向推入键值对
        # 先推值，再推键（由于栈的特性，键会先被处理）
        for key, value in reversed(items):
            self._work_stack.append((value, STATE_INITIAL, None))
            self._work_stack.append((key, STATE_INITIAL, None))
    
    def _process_aggregate(self, node_info: tuple, aux: Any) -> None:
        """处理子摘要的聚合"""
        tag, length = node_info
        
        if tag in (T_LIST, T_TUPLE):
            # 取出最后 length 个摘要并聚合
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
            # 取出最后 length 个摘要，排序后聚合
            children = self._digest_stack[-length:] if length > 0 else []
            if length > 0:
                del self._digest_stack[-length:]
            
            children.sort()  # 对摘要排序以确保确定性顺序
            
            hasher = _get_hasher()
            hasher.update(tag)
            hasher.update(_len_prefix(length))
            for digest in children:
                hasher.update(digest)
            self._digest_stack.append(hasher.digest())
        
        elif tag is T_DICT:
            # 取出最后 2*length 个摘要，配对并按键摘要排序后聚合
            total_digests = 2 * length
            children = self._digest_stack[-total_digests:] if total_digests > 0 else []
            if total_digests > 0:
                del self._digest_stack[-total_digests:]
            
            # 配对为 (key_digest, value_digest)
            pairs = []
            for i in range(0, len(children), 2):
                key_digest = children[i]
                value_digest = children[i + 1] if i + 1 < len(children) else b'\x00' * DIGEST_SIZE
                pairs.append((key_digest, value_digest))
            
            # 按键摘要排序，值摘要作为次要排序键
            pairs.sort(key=lambda kv: (kv[0], kv[1]))
            
            hasher = _get_hasher()
            hasher.update(T_DICT)
            hasher.update(_len_prefix(length))
            for key_digest, value_digest in pairs:
                hasher.update(key_digest)
                hasher.update(value_digest)
            self._digest_stack.append(hasher.digest())
        
        else:
            raise AssertionError(f"未知的容器标签: {tag}")
    
    def _push_digest(self, *parts: bytes) -> None:
        """从多个部分创建摘要并推入栈"""
        hasher = _get_hasher()
        for part in parts:
            hasher.update(part)
        self._digest_stack.append(hasher.digest())
    
    def _push_custom_digest(self, payload: bytes) -> None:
        """为自定义类型推入摘要"""
        hasher = _get_hasher()
        hasher.update(T_CUSTOM)
        hasher.update(_len_prefix(len(payload)))
        hasher.update(payload)
        self._digest_stack.append(hasher.digest())

# 便利的单例实例
_default_hasher = StableHasher()

def stable_hash(obj: Any) -> bytes:
    """
    计算对象的稳定哈希摘要
    
    参数:
        obj: 要哈希的对象（支持 None, bool, int, float, str, bytes, 
             list, tuple, set, frozenset, dict, 以及注册的自定义类型）
    
    返回:
        16字节摘要，跨运行和平台保持一致
    
    异常:
        TypeError: 不支持的类型
    """
    return _default_hasher.hash(obj)

def stable_hash_hex(obj: Any) -> str:
    """
    计算稳定哈希摘要的十六进制字符串形式
    
    参数:
        obj: 要哈希的对象
    
    返回:
        32字符的十六进制字符串表示摘要
    """
    return stable_hash(obj).hex()

def stable_hash_int(obj: Any) -> int:
    """
    计算稳定哈希摘要的整数形式
    
    参数:
        obj: 要哈希的对象
    
    返回:
        摘要的整数表示
    """
    return int.from_bytes(stable_hash(obj), 'big')

# 多对象便利函数
def stable_hash_many(*objects) -> bytes:
    """
    计算多个对象的稳定哈希，如同它们在一个元组中
    
    参数:
        *objects: 要一起哈希的对象
    
    返回:
        对象元组的16字节摘要
    """
    return stable_hash(tuple(objects))

# 配置工具
def set_hash_algorithm(use_blake2b: bool = True) -> None:
    """
    设置哈希算法偏好
    
    参数:
        use_blake2b: 如果为 True 使用 Blake2b（更快），为 False 使用 MD5
    """
    global USE_BLAKE2B
    USE_BLAKE2B = use_blake2b

def get_hash_algorithm() -> str:
    """获取当前哈希算法名称"""
    return "blake2b" if USE_BLAKE2B else "md5"

# 性能工具
class StableHashCache:
    """
    稳定哈希结果的 LRU 缓存，用于加速重复计算
    """
    
    def __init__(self, maxsize: int = 1024):
        self.maxsize = maxsize
        self.cache: Dict[int, bytes] = {}
        self.access_order: list[int] = []
    
    def get(self, obj: Any) -> Optional[bytes]:
        """如果可用，获取缓存的哈希"""
        try:
            # 使用 Python 内置哈希作为缓存键（快速但可能有冲突）
            key = hash(obj)
            if key in self.cache:
                # 移动到末尾（最近使用）
                self.access_order.remove(key)
                self.access_order.append(key)
                return self.cache[key]
        except TypeError:
            # 不可哈希类型，无法缓存
            pass
        return None
    
    def put(self, obj: Any, digest: bytes) -> None:
        """将哈希存储在缓存中"""
        try:
            key = hash(obj)
            if key in self.cache:
                # 更新现有项
                self.access_order.remove(key)
            elif len(self.cache) >= self.maxsize:
                # 移除最少使用的
                lru_key = self.access_order.pop(0)
                del self.cache[lru_key]
            
            self.cache[key] = digest
            self.access_order.append(key)
        except TypeError:
            # 不可哈希类型，无法缓存
            pass
    
    def clear(self) -> None:
        """清空缓存"""
        self.cache.clear()
        self.access_order.clear()

class CachedStableHasher(StableHasher):
    """带 LRU 缓存的稳定哈希器，对重复对象有更好性能"""
    
    def __init__(self, cache_size: int = 1024):
        super().__init__()
        self.cache = StableHashCache(cache_size)
    
    def hash(self, obj: Any) -> bytes:
        """带缓存的哈希计算"""
        # 首先尝试缓存
        cached = self.cache.get(obj)
        if cached is not None:
            return cached
        
        # 计算并缓存
        digest = super().hash(obj)
        self.cache.put(obj, digest)
        return digest

# 常见类型实现示例
def register_common_types():
    """注册一些常见类型的处理器"""
    
    # 复数
    def complex_handler(c: complex) -> bytes:
        return struct.pack(">dd", c.real, c.imag)
    
    # 十进制数（如果可用）
    try:
        from decimal import Decimal
        def decimal_handler(d: Decimal) -> bytes:
            return str(d).encode('ascii')
        register_type(Decimal, decimal_handler)
    except ImportError:
        pass
    
    # UUID（如果可用）
    try:
        from uuid import UUID
        def uuid_handler(u: UUID) -> bytes:
            return u.bytes
        register_type(UUID, uuid_handler)
    except ImportError:
        pass
    
    register_type(complex, complex_handler)

if __name__ == "__main__":
    # 自动注册常见类型
    register_common_types()