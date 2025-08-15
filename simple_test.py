#!/usr/bin/env python3
"""
稳定哈希优化版简单测试
====================

基础功能测试，无外部依赖。
"""

import time
from stable_hash_optimized import stable_hash_hex, stable_hash, register_type

def f():
    """原始测试用例（来自中文规范）"""
    va = {"float": [1.0, 2.0, 3.0, None, 4.0, None, 5.0] * 10}
    vb = {"int": [1, 2, 3, None, 4, None, 5] * 10}
    vc = {"str": ["1", "9", "2", "3", "None"] * 10 + ["4", "None", "5"] * 10}
    vd = {"left": va, "right": vb}
    ve = {"left": vc, "right": vd}
    f_ = {"single": ve}
    return f_

def test_basic_functionality():
    """测试基础稳定哈希功能"""
    print("测试基础功能...")
    
    test_cases = [
        None,
        True,
        False,
        42,
        3.14159,
        "Hello 世界 🌍",
        b"binary data",
        [1, 2, 3, None],
        (1, 2, 3),
        {1, 2, 3},
        {"key": "value", "nested": {"data": [1, 2, 3]}},
        f()
    ]
    
    errors = 0
    for i, obj in enumerate(test_cases):
        try:
            hash_result = stable_hash_hex(obj)
            print(f"✓ 用例 {i+1}: {type(obj).__name__} -> {hash_result[:16]}...")
        except Exception as e:
            print(f"✗ 用例 {i+1}: {type(obj).__name__} -> 错误: {e}")
            errors += 1
    
    if errors == 0:
        print("✓ 所有基础测试通过!")
    else:
        print(f"✗ {errors} 个测试失败")
    
    return errors == 0

def test_consistency():
    """测试哈希结果在多次运行中的一致性"""
    print("\n测试一致性...")
    
    test_obj = f()
    hashes = []
    
    for i in range(5):
        h = stable_hash_hex(test_obj)
        hashes.append(h)
    
    if len(set(hashes)) == 1:
        print(f"✓ 一致性测试通过: {hashes[0]}")
        return True
    else:
        print(f"✗ 哈希不一致: {hashes}")
        return False

def test_deep_nesting():
    """测试深度嵌套处理"""
    print("\n测试深度嵌套...")
    
    # 创建嵌套结构
    current = "end"
    for i in range(1000):
        current = {"level": i, "next": current}
    
    try:
        start_time = time.perf_counter()
        hash_result = stable_hash_hex(current)
        elapsed = time.perf_counter() - start_time
        print(f"✓ 深度嵌套 (1000 层): {hash_result[:16]}... ({elapsed:.3f}s)")
        return True
    except Exception as e:
        print(f"✗ 深度嵌套失败: {e}")
        return False

def test_custom_types():
    """测试自定义类型支持"""
    print("\n测试自定义类型...")
    
    class Point:
        def __init__(self, x, y):
            self.x = x
            self.y = y
    
    # 测试未注册（应该失败）
    point = Point(1.0, 2.0)
    try:
        stable_hash_hex(point)
        print("✗ 自定义类型在未注册时也能工作")
        return False
    except TypeError:
        print("✓ 自定义类型正确拒绝未注册")
    
    # 注册并测试
    def point_handler(p):
        return f"point:{p.x},{p.y}".encode()
    
    register_type(Point, point_handler)
    
    try:
        hash_result = stable_hash_hex(point)
        print(f"✓ 自定义类型注册后工作: {hash_result[:16]}...")
        
        # 测试一致性
        point2 = Point(1.0, 2.0)
        hash_result2 = stable_hash_hex(point2)
        if hash_result == hash_result2:
            print("✓ 自定义类型哈希一致")
            return True
        else:
            print("✗ 自定义类型哈希不一致")
            return False
    except Exception as e:
        print(f"✗ 自定义类型注册失败: {e}")
        return False

def test_special_values():
    """测试特殊浮点值"""
    print("\n测试特殊值...")
    
    special_values = [
        0.0, -0.0, float('inf'), float('-inf'), float('nan')
    ]
    
    errors = 0
    for val in special_values:
        try:
            hash_result = stable_hash_hex(val)
            print(f"✓ {val}: {hash_result[:16]}...")
        except Exception as e:
            print(f"✗ {val}: {e}")
            errors += 1
    
    # 测试 -0.0 和 0.0 产生相同哈希
    try:
        hash_pos_zero = stable_hash_hex(0.0)
        hash_neg_zero = stable_hash_hex(-0.0)
        if hash_pos_zero == hash_neg_zero:
            print("✓ -0.0 和 0.0 产生相同哈希（已归一化）")
        else:
            print("✗ -0.0 和 0.0 产生不同哈希")
            errors += 1
    except Exception as e:
        print(f"✗ 零值归一化测试失败: {e}")
        errors += 1
    
    return errors == 0

def run_performance_test():
    """简单性能测试"""
    print("\n运行性能测试...")
    
    # 创建测试数据
    test_data = []
    for i in range(1000):
        test_data.append({
            f"key_{i}": [j for j in range(10)],
            "nested": {"value": i * i}
        })
    
    start_time = time.perf_counter()
    for obj in test_data:
        stable_hash(obj)
    elapsed = time.perf_counter() - start_time
    
    objects_per_second = len(test_data) / elapsed
    print(f"性能: {elapsed:.3f}s 处理 {len(test_data)} 对象 ({objects_per_second:.0f} obj/s)")

def main():
    """运行所有测试"""
    print("稳定哈希优化版 - 简单测试套件")
    print("=" * 50)
    
    tests = [
        test_basic_functionality,
        test_consistency,
        test_deep_nesting,
        test_custom_types,
        test_special_values
    ]
    
    passed = 0
    for test_func in tests:
        if test_func():
            passed += 1
    
    run_performance_test()
    
    print(f"\n总结: {passed}/{len(tests)} 测试通过")
    
    if passed == len(tests):
        print("🎉 所有测试通过 - 实现工作正常!")
    else:
        print("❌ 部分测试失败 - 需要检查")
    
    return passed == len(tests)

if __name__ == "__main__":
    main()