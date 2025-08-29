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
    # Note: Not registering numpy to avoid errors when it's not available
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