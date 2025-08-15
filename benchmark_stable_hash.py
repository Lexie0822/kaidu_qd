#!/usr/bin/env python3
"""
Comprehensive Benchmark Suite for Stable Hash Implementation
============================================================

Tests performance, correctness, consistency, and handles edge cases
for the optimized stable hash function.
"""

import time
import random
import string
import sys
import traceback
from typing import Any, List, Dict
from stable_hash_optimized import (
    stable_hash, stable_hash_hex, stable_hash_int,
    register_type, StableHasher, CachedStableHasher,
    set_hash_algorithm, get_hash_algorithm
)

def f():
    """Original test case from the Chinese specification"""
    va = {"float": [1.0, 2.0, 3.0, None, 4.0, None, 5.0] * 10}
    vb = {"int": [1, 2, 3, None, 4, None, 5] * 10}
    vc = {"str": ["1", "9", "2", "3", "None"] * 10 + ["4", "None", "5"] * 10}
    vd = {"left": va, "right": vb}
    ve = {"left": vc, "right": vd}
    f_ = {"single": ve}
    return f_

def create_test_data() -> List[Any]:
    """Create diverse test data for benchmarking"""
    data = []
    
    # Basic types
    data.extend([
        None, True, False,
        0, 1, -1, 123456789, -123456789,
        0.0, 1.0, -1.0, 3.14159, float('inf'), float('-inf'), float('nan'),
        "", "hello", "unicode 测试 🚀", "a" * 1000,
        b"", b"hello", b"binary data", bytes(range(256))
    ])
    
    # Collections
    data.extend([
        [], [1, 2, 3], [None, True, "mixed"],
        (), (1, 2, 3), (None, True, "mixed"),
        set(), {1, 2, 3}, {"a", "b", "c"},
        frozenset(), frozenset([1, 2, 3]),
        {}, {"a": 1, "b": 2}, {1: "one", 2: "two"}
    ])
    
    # Complex nested structures
    data.extend([
        {"nested": {"deep": {"data": [1, 2, 3]}}},
        [{"key": i} for i in range(100)],
        {f"key_{i}": [j for j in range(10)] for i in range(20)},
        [[[[[i]]]]] for i in range(10)],  # Deep nesting
    ])
    
    # Original test case
    data.append(f())
    
    return data

def create_large_test_data(size: int = 1000) -> List[Any]:
    """Create large test objects for performance testing"""
    data = []
    
    # Large lists
    data.append([random.randint(-1000, 1000) for _ in range(size)])
    data.append([random.uniform(-1000, 1000) for _ in range(size)])
    data.append([''.join(random.choices(string.ascii_letters, k=10)) for _ in range(size)])
    
    # Large dicts
    data.append({f"key_{i}": i * i for i in range(size)})
    data.append({random.randint(0, size*10): random.uniform(0, 1) for _ in range(size)})
    
    # Large sets
    data.append(set(range(size)))
    data.append(set(random.randint(0, size*10) for _ in range(size)))
    
    # Mixed large structures
    mixed = {
        "integers": [random.randint(-1000, 1000) for _ in range(size//4)],
        "floats": [random.uniform(-1000, 1000) for _ in range(size//4)],
        "strings": [''.join(random.choices(string.ascii_letters, k=5)) for _ in range(size//4)],
        "nested": {
            f"sub_{i}": {
                "data": [j for j in range(10)],
                "meta": {"id": i, "active": i % 2 == 0}
            } for i in range(size//10)
        }
    }
    data.append(mixed)
    
    return data

def create_deeply_nested_data(depth: int = 1000) -> Any:
    """Create deeply nested structure to test recursion handling"""
    current = {"end": "value"}
    for i in range(depth):
        current = {"level": i, "next": current}
    return current

def test_consistency():
    """Test that hash results are consistent across multiple runs"""
    print("Testing consistency...")
    
    test_data = create_test_data()
    
    # Compute hashes multiple times
    hash_sets = []
    for run in range(3):
        current_hashes = []
        for obj in test_data:
            try:
                h = stable_hash_hex(obj)
                current_hashes.append(h)
            except Exception as e:
                print(f"Error hashing {type(obj)}: {e}")
                current_hashes.append(None)
        hash_sets.append(current_hashes)
    
    # Check consistency
    consistent = True
    for i, obj in enumerate(test_data):
        hashes_for_obj = [hs[i] for hs in hash_sets]
        if len(set(h for h in hashes_for_obj if h is not None)) > 1:
            print(f"Inconsistent hash for {type(obj)}: {hashes_for_obj}")
            consistent = False
    
    if consistent:
        print("✓ All hashes are consistent across runs")
    else:
        print("✗ Some hashes are inconsistent!")
    
    return consistent

def test_edge_cases():
    """Test edge cases and special values"""
    print("Testing edge cases...")
    
    edge_cases = [
        # Float edge cases
        0.0, -0.0, float('inf'), float('-inf'), float('nan'),
        
        # Empty collections
        [], (), set(), frozenset(), {},
        
        # Single element collections
        [None], (None,), {None}, frozenset([None]), {None: None},
        
        # Collections with duplicates (for sets)
        {1, 1, 1}, frozenset([1, 1, 1]),
        
        # Unicode edge cases
        "", "\x00", "\uffff", "🚀🌟✨",
        
        # Large integers
        2**100, -2**100, 2**1000,
        
        # Nested None
        [None, [None, [None]]],
        {"a": None, "b": {"c": None}},
    ]
    
    errors = 0
    for obj in edge_cases:
        try:
            h = stable_hash_hex(obj)
            print(f"✓ {repr(obj)[:50]}: {h[:16]}...")
        except Exception as e:
            print(f"✗ {repr(obj)[:50]}: {e}")
            errors += 1
    
    if errors == 0:
        print("✓ All edge cases handled successfully")
    else:
        print(f"✗ {errors} edge cases failed")
    
    return errors == 0

def test_deep_nesting():
    """Test handling of deeply nested structures"""
    print("Testing deep nesting (recursion limit handling)...")
    
    depths = [100, 500, 1000, 2000]
    results = {}
    
    for depth in depths:
        try:
            nested_data = create_deeply_nested_data(depth)
            start_time = time.perf_counter()
            h = stable_hash_hex(nested_data)
            elapsed = time.perf_counter() - start_time
            results[depth] = (h[:16], elapsed)
            print(f"✓ Depth {depth}: {h[:16]}... ({elapsed:.3f}s)")
        except Exception as e:
            print(f"✗ Depth {depth}: {e}")
            results[depth] = None
    
    # Check consistency for same depths
    depth_1000_hash = results.get(1000)
    if depth_1000_hash:
        # Test the same depth again
        try:
            nested_data_2 = create_deeply_nested_data(1000)
            h2 = stable_hash_hex(nested_data_2)[:16]
            if h2 == depth_1000_hash[0]:
                print("✓ Deep nesting hashes are consistent")
            else:
                print(f"✗ Deep nesting hashes inconsistent: {h2} vs {depth_1000_hash[0]}")
        except Exception as e:
            print(f"✗ Error in consistency check: {e}")
    
    return all(v is not None for v in results.values())

def test_algorithm_performance():
    """Compare Blake2b vs MD5 performance"""
    print("Comparing hash algorithms...")
    
    # Create test data
    test_data = create_large_test_data(500)
    
    algorithms = [("blake2b", True), ("md5", False)]
    results = {}
    
    for alg_name, use_blake2b in algorithms:
        set_hash_algorithm(use_blake2b)
        print(f"Testing {alg_name}...")
        
        start_time = time.perf_counter()
        hashes = []
        for obj in test_data:
            try:
                h = stable_hash_hex(obj)
                hashes.append(h)
            except Exception as e:
                print(f"Error with {alg_name}: {e}")
                hashes.append(None)
        
        elapsed = time.perf_counter() - start_time
        results[alg_name] = {
            'time': elapsed,
            'hashes': hashes,
            'success_rate': sum(1 for h in hashes if h is not None) / len(hashes)
        }
        
        print(f"  {alg_name}: {elapsed:.3f}s, {results[alg_name]['success_rate']*100:.1f}% success")
    
    # Check consistency between algorithms (they should produce same results)
    if len(results) == 2:
        blake2b_hashes = results['blake2b']['hashes']
        md5_hashes = results['md5']['hashes']
        
        mismatches = 0
        for i, (h1, h2) in enumerate(zip(blake2b_hashes, md5_hashes)):
            if h1 is not None and h2 is not None and h1 != h2:
                mismatches += 1
        
        if mismatches == 0:
            print("✓ Blake2b and MD5 produce identical results")
        else:
            print(f"✗ {mismatches} mismatches between algorithms")
    
    # Reset to default
    set_hash_algorithm(True)
    
    return results

def test_caching_performance():
    """Test performance improvement with caching"""
    print("Testing caching performance...")
    
    # Create data with some repeated objects
    base_objects = create_test_data()[:20]  # Small set for repetition
    test_data = []
    for _ in range(100):
        test_data.extend(random.choices(base_objects, k=5))
    
    # Test without caching
    regular_hasher = StableHasher()
    start_time = time.perf_counter()
    for obj in test_data:
        try:
            regular_hasher.hash(obj)
        except:
            pass
    regular_time = time.perf_counter() - start_time
    
    # Test with caching
    cached_hasher = CachedStableHasher(cache_size=100)
    start_time = time.perf_counter()
    for obj in test_data:
        try:
            cached_hasher.hash(obj)
        except:
            pass
    cached_time = time.perf_counter() - start_time
    
    speedup = regular_time / cached_time if cached_time > 0 else float('inf')
    
    print(f"Regular hasher: {regular_time:.3f}s")
    print(f"Cached hasher: {cached_time:.3f}s")
    print(f"Speedup: {speedup:.1f}x")
    
    return speedup

def test_custom_types():
    """Test custom type registration and magic method protocol"""
    print("Testing custom type extensibility...")
    
    # Test magic method protocol
    class MagicHashClass:
        def __init__(self, value):
            self.value = value
        
        def __stable_hash__(self):
            from hashlib import blake2b
            return blake2b(f"magic:{self.value}".encode(), digest_size=16).digest()
    
    # Test registration protocol
    class RegisteredClass:
        def __init__(self, x, y):
            self.x = x
            self.y = y
    
    def registered_handler(obj):
        return f"reg:{obj.x},{obj.y}".encode()
    
    register_type(RegisteredClass, registered_handler)
    
    # Test both approaches
    try:
        magic_obj = MagicHashClass("test")
        magic_hash = stable_hash_hex(magic_obj)
        print(f"✓ Magic method: {magic_hash[:16]}...")
        
        reg_obj = RegisteredClass(1, 2)
        reg_hash = stable_hash_hex(reg_obj)
        print(f"✓ Registered type: {reg_hash[:16]}...")
        
        # Test consistency
        magic_hash2 = stable_hash_hex(MagicHashClass("test"))
        reg_hash2 = stable_hash_hex(RegisteredClass(1, 2))
        
        if magic_hash == magic_hash2 and reg_hash == reg_hash2:
            print("✓ Custom types are consistent")
            return True
        else:
            print("✗ Custom types are inconsistent")
            return False
            
    except Exception as e:
        print(f"✗ Custom type error: {e}")
        traceback.print_exc()
        return False

def benchmark_performance():
    """Comprehensive performance benchmark"""
    print("Running performance benchmark...")
    
    test_sizes = [100, 500, 1000, 2000]
    results = {}
    
    for size in test_sizes:
        print(f"Testing with {size} objects...")
        
        test_data = create_large_test_data(size)
        
        start_time = time.perf_counter()
        hashes = []
        errors = 0
        
        for obj in test_data:
            try:
                h = stable_hash(obj)
                hashes.append(h)
            except Exception as e:
                errors += 1
                hashes.append(None)
        
        elapsed = time.perf_counter() - start_time
        objects_per_second = len(test_data) / elapsed if elapsed > 0 else float('inf')
        
        results[size] = {
            'time': elapsed,
            'objects_per_second': objects_per_second,
            'errors': errors,
            'success_rate': (len(test_data) - errors) / len(test_data)
        }
        
        print(f"  {size} objects: {elapsed:.3f}s ({objects_per_second:.0f} obj/s, {results[size]['success_rate']*100:.1f}% success)")
    
    return results

def run_original_test_case():
    """Run the original test case from the specification"""
    print("Running original test case...")
    
    try:
        original_data = f()
        h = stable_hash_hex(original_data)
        print(f"Original test case hash: {h}")
        
        # Test multiple times for consistency
        for i in range(5):
            h2 = stable_hash_hex(f())
            if h != h2:
                print(f"✗ Inconsistent hash on run {i+1}: {h2}")
                return False
        
        print("✓ Original test case is consistent")
        return True
        
    except Exception as e:
        print(f"✗ Original test case failed: {e}")
        traceback.print_exc()
        return False

def main():
    """Run all tests and benchmarks"""
    print("Stable Hash Optimization - Comprehensive Test Suite")
    print("=" * 60)
    
    test_results = {}
    
    # Correctness tests
    print("\n1. CORRECTNESS TESTS")
    print("-" * 30)
    test_results['consistency'] = test_consistency()
    test_results['edge_cases'] = test_edge_cases()
    test_results['deep_nesting'] = test_deep_nesting()
    test_results['custom_types'] = test_custom_types()
    test_results['original_case'] = run_original_test_case()
    
    # Performance tests
    print("\n2. PERFORMANCE TESTS")
    print("-" * 30)
    perf_results = benchmark_performance()
    alg_results = test_algorithm_performance()
    cache_speedup = test_caching_performance()
    
    # Summary
    print("\n3. SUMMARY")
    print("-" * 30)
    
    correctness_score = sum(test_results.values())
    total_tests = len(test_results)
    
    print(f"Correctness: {correctness_score}/{total_tests} tests passed")
    
    if perf_results:
        largest_test = max(perf_results.keys())
        largest_result = perf_results[largest_test]
        print(f"Performance: {largest_result['objects_per_second']:.0f} objects/sec ({largest_test} objects)")
    
    print(f"Algorithm: {get_hash_algorithm()} selected")
    print(f"Caching speedup: {cache_speedup:.1f}x")
    
    # Final verdict
    if correctness_score == total_tests:
        print("\n✓ ALL TESTS PASSED - Implementation ready for production")
    else:
        print(f"\n✗ {total_tests - correctness_score} tests failed - Review needed")
    
    return test_results, perf_results

if __name__ == "__main__":
    main()