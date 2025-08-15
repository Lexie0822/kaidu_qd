#!/usr/bin/env python3
"""
Simple Test for Optimized Stable Hash
=====================================

Basic functionality test without external dependencies.
"""

import time
from stable_hash_optimized import stable_hash_hex, stable_hash, register_type

def f():
    """Original test case from the Chinese specification"""
    va = {"float": [1.0, 2.0, 3.0, None, 4.0, None, 5.0] * 10}
    vb = {"int": [1, 2, 3, None, 4, None, 5] * 10}
    vc = {"str": ["1", "9", "2", "3", "None"] * 10 + ["4", "None", "5"] * 10}
    vd = {"left": va, "right": vb}
    ve = {"left": vc, "right": vd}
    f_ = {"single": ve}
    return f_

def test_basic_functionality():
    """Test basic stable hash functionality"""
    print("Testing basic functionality...")
    
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
            print(f"✓ Case {i+1}: {type(obj).__name__} -> {hash_result[:16]}...")
        except Exception as e:
            print(f"✗ Case {i+1}: {type(obj).__name__} -> ERROR: {e}")
            errors += 1
    
    if errors == 0:
        print("✓ All basic tests passed!")
    else:
        print(f"✗ {errors} tests failed")
    
    return errors == 0

def test_consistency():
    """Test that hashes are consistent across multiple runs"""
    print("\nTesting consistency...")
    
    test_obj = f()
    hashes = []
    
    for i in range(5):
        h = stable_hash_hex(test_obj)
        hashes.append(h)
    
    if len(set(hashes)) == 1:
        print(f"✓ Consistency test passed: {hashes[0]}")
        return True
    else:
        print(f"✗ Inconsistent hashes: {hashes}")
        return False

def test_deep_nesting():
    """Test handling of deep nesting"""
    print("\nTesting deep nesting...")
    
    # Create nested structure
    current = "end"
    for i in range(1000):
        current = {"level": i, "next": current}
    
    try:
        start_time = time.perf_counter()
        hash_result = stable_hash_hex(current)
        elapsed = time.perf_counter() - start_time
        print(f"✓ Deep nesting (1000 levels): {hash_result[:16]}... ({elapsed:.3f}s)")
        return True
    except Exception as e:
        print(f"✗ Deep nesting failed: {e}")
        return False

def test_custom_types():
    """Test custom type support"""
    print("\nTesting custom types...")
    
    class Point:
        def __init__(self, x, y):
            self.x = x
            self.y = y
    
    # Test without registration (should fail)
    point = Point(1.0, 2.0)
    try:
        stable_hash_hex(point)
        print("✗ Custom type worked without registration")
        return False
    except TypeError:
        print("✓ Custom type properly rejected without registration")
    
    # Register and test
    def point_handler(p):
        return f"point:{p.x},{p.y}".encode()
    
    register_type(Point, point_handler)
    
    try:
        hash_result = stable_hash_hex(point)
        print(f"✓ Custom type with registration: {hash_result[:16]}...")
        
        # Test consistency
        point2 = Point(1.0, 2.0)
        hash_result2 = stable_hash_hex(point2)
        if hash_result == hash_result2:
            print("✓ Custom type hashes are consistent")
            return True
        else:
            print("✗ Custom type hashes are inconsistent")
            return False
    except Exception as e:
        print(f"✗ Custom type registration failed: {e}")
        return False

def test_special_values():
    """Test special floating point values"""
    print("\nTesting special values...")
    
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
    
    # Test that -0.0 and 0.0 produce same hash
    try:
        hash_pos_zero = stable_hash_hex(0.0)
        hash_neg_zero = stable_hash_hex(-0.0)
        if hash_pos_zero == hash_neg_zero:
            print("✓ -0.0 and 0.0 produce same hash (normalized)")
        else:
            print("✗ -0.0 and 0.0 produce different hashes")
            errors += 1
    except Exception as e:
        print(f"✗ Zero normalization test failed: {e}")
        errors += 1
    
    return errors == 0

def run_performance_test():
    """Simple performance test"""
    print("\nRunning performance test...")
    
    # Create test data
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
    print(f"Performance: {elapsed:.3f}s for {len(test_data)} objects ({objects_per_second:.0f} obj/s)")

def main():
    """Run all tests"""
    print("Optimized Stable Hash - Simple Test Suite")
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
    
    print(f"\nSUMMARY: {passed}/{len(tests)} tests passed")
    
    if passed == len(tests):
        print("🎉 ALL TESTS PASSED - Implementation is working correctly!")
    else:
        print("❌ Some tests failed - Review needed")
    
    return passed == len(tests)

if __name__ == "__main__":
    main()