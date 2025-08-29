#!/usr/bin/env python3
"""
Test suite for rpyc_import_bridge.
Keep it simple: run server, run this, see results.
"""
import rpyc
from rpyc_import_bridge import RPyCImportBridge
import sys
import traceback

# Test tracking
tests_passed = 0
tests_failed = 0

def test(name, func):
    """Run a test and track results."""
    global tests_passed, tests_failed
    try:
        print(f"  {name}... ", end="", flush=True)
        func()
        print("✓ PASS")
        tests_passed += 1
    except Exception as e:
        print(f"✗ FAIL: {e}")
        tests_failed += 1
        if "-v" in sys.argv:  # Verbose mode
            traceback.print_exc()

def main():
    print("=== RPyC Import Bridge Test Suite ===\n")
    
    # Connect to server
    try:
        c = rpyc.connect("127.0.0.1", 6070)
        print("✓ Connected to test server")
    except Exception as e:
        print(f"✗ Failed to connect to server: {e}")
        print("Make sure the server is running: python test/server/test_server.py")
        return 1
    
    # Initialize bridge
    bridge = RPyCImportBridge(c)
    bridge.register_remote_module("sample_module")
    bridge.register_remote_module("test_package")
    bridge.register_remote_module("advanced_classes")
    bridge.register_remote_module("data_types")
    bridge.register_remote_module("nested_package")
    bridge.register_remote_module("numpy")
    bridge.install_import_hooks()
    print("✓ Bridge initialized\n")
    
    # ==========================================
    print("1. Simple Module Tests (sample_module):")
    
    def test_simple_import():
        import sample_module
        assert hasattr(sample_module, '__getattr__'), "Module should have __getattr__"
        assert not hasattr(sample_module, '__path__'), "Simple module should not have __path__"
    
    def test_function_import():
        from sample_module import simple_function
        result = simple_function(5)
        assert result == 10, f"Expected 10, got {result}"
    
    def test_class_import():
        from sample_module import SimpleClass
        obj = SimpleClass(99)
        assert obj.get_value() == 99, f"Expected 99, got {obj.get_value()}"
    
    def test_multiple_imports():
        from sample_module import simple_function as f1
        from sample_module import simple_function as f2
        assert f1 is f2, "Multiple imports should return same cached object"
    
    def test_nonexistent_attribute():
        import sample_module
        try:
            from sample_module import nonexistent_thing
            assert False, "Should have raised ImportError"
        except ImportError:
            pass  # Expected
    
    test("Import simple module", test_simple_import)
    test("Import function from module", test_function_import)
    test("Import class from module", test_class_import)
    test("Multiple imports are cached", test_multiple_imports)
    test("Nonexistent attributes raise ImportError", test_nonexistent_attribute)
    
    # ==========================================
    print("\n2. Package Tests (test_package):")
    
    def test_package_import():
        import test_package
        assert hasattr(test_package, '__getattr__'), "Package should have __getattr__"
        assert hasattr(test_package, '__path__'), "Package should have __path__"
        assert test_package.__path__ == [], "Package __path__ should be empty list"
    
    def test_package_level_function():
        from test_package import package_function
        result = package_function(5)
        assert result == 105, f"Expected 105, got {result}"
    
    def test_package_level_class():
        from test_package import PackageClass
        obj = PackageClass(50)
        assert obj.get_value() == 50, f"Expected 50, got {obj.get_value()}"
    
    def test_package_level_variable():
        from test_package import package_version
        assert package_version == "1.0.0", f"Expected '1.0.0', got {package_version}"
    
    def test_submodule_import():
        # This is the key test that was failing with binaryninja
        from test_package import submodule
        assert hasattr(submodule, 'submodule_function'), "Submodule should have functions"
    
    def test_submodule_function():
        from test_package.submodule import submodule_function
        result = submodule_function(3, 4)
        assert result == 12, f"Expected 12, got {result}"
    
    def test_submodule_class():
        from test_package.submodule import SubmoduleClass
        obj = SubmoduleClass(3)
        result = obj.multiply(5)
        assert result == 15, f"Expected 15, got {result}"
    
    def test_submodule_constants():
        from test_package.submodule import SUBMODULE_CONSTANT, MAGIC_NUMBER
        assert SUBMODULE_CONSTANT == "I am a constant"
        assert MAGIC_NUMBER == 42
    
    test("Import package module", test_package_import)
    test("Import function from package", test_package_level_function)
    test("Import class from package", test_package_level_class)
    test("Import variable from package", test_package_level_variable)
    test("Import submodule from package", test_submodule_import)
    test("Import function from submodule", test_submodule_function)
    test("Import class from submodule", test_submodule_class)
    test("Import constants from submodule", test_submodule_constants)
    
    # ==========================================
    print("\n3. Edge Case Tests:")
    
    def test_repeated_imports():
        import sample_module as sm1
        import sample_module as sm2
        assert sm1 is sm2, "Repeated imports should return same module"
    
    def test_mixed_import_styles():
        import test_package
        from test_package import package_function
        # Should work without conflicts
        assert test_package.package_function is package_function
    
    def test_module_attributes():
        import sample_module
        assert sample_module.__name__ == "sample_module"
        assert "<proxy for sample_module>" in sample_module.__file__
    
    test("Repeated imports return same object", test_repeated_imports)
    test("Mixed import styles work", test_mixed_import_styles)
    test("Module has correct attributes", test_module_attributes)
    
    # ==========================================
    print("\n4. Advanced Class Tests (advanced_classes):")
    
    def test_inheritance():
        from advanced_classes import BaseClass, DerivedClass
        base = BaseClass(5)
        derived = DerivedClass(10, 20)
        assert base.base_method() == "base: 5"
        assert derived.base_method() == "derived: 10"
        assert derived.derived_only_method() == "extra: 20"
    
    def test_class_methods():
        from advanced_classes import BaseClass
        obj = BaseClass.create_default()
        assert obj.value == 42
        assert BaseClass.static_helper(5) == 500
    
    def test_properties():
        from advanced_classes import DerivedClass, PropertyClass
        derived = DerivedClass(10, 5)
        assert derived.computed_property == 15
        # note: property setters blocked by rpyc security - this is expected
        
        prop_obj = PropertyClass()
        assert prop_obj.read_only == 100
        # read_write property getter works
        initial_value = prop_obj.read_write
        assert isinstance(initial_value, int)  # verify it's accessible
    
    def test_special_methods():
        from advanced_classes import SpecialMethodsClass
        obj = SpecialMethodsClass([1, 2, 3])
        assert len(obj) == 3
        assert obj[0] == 1
        assert 2 in obj
        obj[1] = 99
        assert obj[1] == 99
        count = obj(4)  # __call__
        assert count == 4
    
    test("Class inheritance works", test_inheritance)
    test("Class and static methods work", test_class_methods)
    test("Properties work", test_properties)  
    test("Special methods work", test_special_methods)
    
    # ==========================================
    print("\n5. Data Types Tests (data_types):")
    
    def test_basic_data_types():
        from data_types import SIMPLE_LIST, SIMPLE_DICT, SIMPLE_TUPLE
        assert SIMPLE_LIST[3] == "hello"
        assert SIMPLE_DICT["nested"]["inner"] == "value"
        assert SIMPLE_TUPLE[1] == "two"
    
    def test_complex_structures():
        from data_types import NESTED_STRUCTURE, DEFAULT_DICT, NAMED_TUPLE
        deep_val = NESTED_STRUCTURE["level1"]["level2"]["level3"][2]["very"]
        assert deep_val == "deep"
        # remote lists compare by content, not identity
        key1_list = DEFAULT_DICT["key1"]
        assert len(key1_list) == 3
        assert key1_list[0] == 1 and key1_list[1] == 2 and key1_list[2] == 3
        assert NAMED_TUPLE.x == 10
    
    def test_dataclass():
        from data_types import PERSON_INSTANCE, Person
        assert PERSON_INSTANCE.name == "Alice"
        assert "Alice" in PERSON_INSTANCE.greet()
        new_person = Person("Bob", 25)
        assert new_person.age == 25
    
    def test_data_functions():
        from data_types import get_large_list, get_nested_dict
        big_list = get_large_list(100)
        assert len(big_list) == 100
        assert big_list[50] == 50
        nested = get_nested_dict(2)
        assert nested["level"] == 2
        assert nested["child"]["level"] == 1
    
    test("Basic data types work", test_basic_data_types)
    test("Complex data structures work", test_complex_structures)
    test("Dataclass instances work", test_dataclass)
    test("Data-returning functions work", test_data_functions)
    
    # ==========================================
    print("\n6. Nested Package Tests (nested_package):")
    
    def test_nested_imports():
        from nested_package import top_level_func, TOP_LEVEL_VAR
        from nested_package.sub import sub_func
        from nested_package.sub.deep_module import deep_function, DeepClass
        
        assert top_level_func() == "top level"
        assert TOP_LEVEL_VAR == "nested package root"
        assert sub_func() == "sub package"
        assert deep_function("test") == "deep: test"
        
        deep_obj = DeepClass("nested")
        assert deep_obj.get_deep() == "very nested"
    
    test("Deep nested package imports work", test_nested_imports)
    
    # ==========================================
    print("\n7. Real-World Package Tests (numpy):")
    
    def test_numpy_basic():
        import numpy
        import numpy as np
        from numpy import array, zeros
        
        arr = np.array([1, 2, 3])
        assert arr.shape == (3,)
        assert arr[1] == 2
        
        zero_arr = zeros((2, 2))
        assert zero_arr.shape == (2, 2)
    
    def test_numpy_submodules():
        from numpy import linalg
        from numpy.linalg import norm
        import numpy as np
        
        vec = np.array([3, 4])
        length = norm(vec)
        assert abs(length - 5.0) < 0.01
    
    test("Numpy basic functionality", test_numpy_basic)
    test("Numpy submodule imports", test_numpy_submodules)
    
    # ==========================================
    print(f"\n=== Test Results ===")
    total = tests_passed + tests_failed
    print(f"Tests run: {total}")
    print(f"Passed: {tests_passed}")
    print(f"Failed: {tests_failed}")
    
    if tests_failed == 0:
        print("✓ ALL TESTS PASSED!")
        return 0
    else:
        print("✗ SOME TESTS FAILED!")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)