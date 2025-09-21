#!/usr/bin/env python3
"""
Test script to validate all example files are working correctly.
This script runs each example and reports success/failure status.
"""

import subprocess
import sys
from pathlib import Path


def test_example(example_file):
    """Test a single example file."""
    try:
        # Run the example with a timeout
        result = subprocess.run(
            [sys.executable, str(example_file)],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=Path(__file__).parent,
        )

        if result.returncode == 0:
            print(f"✅ {example_file.name}")
            return True
        else:
            print(f"❌ {example_file.name} (exit code: {result.returncode})")
            if result.stderr:
                print(f"   Error: {result.stderr.strip()}")
            return False

    except subprocess.TimeoutExpired:
        print(f"⏰ {example_file.name} (timeout)")
        return False
    except Exception as e:
        print(f"❌ {example_file.name} (exception: {e})")
        return False


def test_server_example(example_file):
    """Test a server example file - these start servers that need special handling."""
    try:
        # For server examples, we just check if they start without errors
        # and then terminate them after a few seconds
        process = subprocess.Popen(
            [sys.executable, str(example_file)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=Path(__file__).parent,
        )

        # Wait a few seconds to see if the server starts properly
        try:
            stdout, stderr = process.communicate(timeout=5)
            # If process exits within 5 seconds, check the result
            if process.returncode == 0:
                print(f"✅ {example_file.name} (completed)")
                return True
            else:
                print(f"❌ {example_file.name} (exit code: {process.returncode})")
                if stderr:
                    print(f"   Error: {stderr.strip()}")
                return False
        except subprocess.TimeoutExpired:
            # If still running after 5 seconds, assume it started successfully
            # and terminate it
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()

            print(f"✅ {example_file.name} (server started)")
            return True

    except Exception as e:
        print(f"❌ {example_file.name} (exception: {e})")
        return False


def main():
    """Test all example files."""
    print("🧪 Testing jvspatial example files...")
    print("=" * 50)

    examples_dir = Path(__file__).parent

    # List of key example files to test
    key_examples = [
        "agent_graph.py",
        "travel_graph.py",
        "crud_demo.py",
        "orm_demo.py",
        "walker_traversal_demo.py",
        "enhanced_nodes_filtering.py",
        "modern_query_interface.py",
        "multi_target_hooks_demo.py",
        "object_pagination_demo.py",
        "traversal_demo.py",
        "semantic_filtering.py",
        "unified_query_interface_example.py",
        "custom_database_example.py",
        "database_switching_example.py",
        "graphcontext_demo.py",
        "testing_with_graphcontext.py",
    ]

    # Server examples (may have dependency issues)
    server_examples = [
        "simple_dynamic_example.py",
        "dynamic_server_demo.py",
        "endpoint_decorator_demo.py",
        "endpoint_respond_demo.py",
        "server_demo.py",
        "fastapi_server.py",
        "dynamic_endpoint_removal.py",
    ]

    passed = 0
    failed = 0

    print("\n📊 Core Examples:")
    print("-" * 30)

    for example_name in key_examples:
        example_path = examples_dir / example_name
        if example_path.exists():
            if test_example(example_path):
                passed += 1
            else:
                failed += 1
        else:
            print(f"❓ {example_name} (not found)")
            failed += 1

    print(f"\n🌐 Server Examples (may have dependencies):")
    print("-" * 45)

    for example_name in server_examples:
        example_path = examples_dir / example_name
        if example_path.exists():
            if test_server_example(example_path):
                passed += 1
            else:
                failed += 1
        else:
            print(f"❓ {example_name} (not found)")
            failed += 1

    print(f"\n📈 Summary:")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"📊 Total: {passed + failed}")

    if failed == 0:
        print("\n🎉 All examples are working correctly!")
        return 0
    else:
        print(f"\n⚠️  {failed} examples have issues")
        return 1


if __name__ == "__main__":
    sys.exit(main())
