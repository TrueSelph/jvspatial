#!/usr/bin/env python3
"""Test script to validate all example files.

This script runs each example and reports success/failure status.
"""

import os
import subprocess
import sys
from pathlib import Path


def run_example_group(examples_dir, examples, title, description):
    """Run a group of examples and return results."""
    print(f"{title}")
    print("-" * 50)
    print(description)
    print()

    passed = failed = 0
    for example_name in examples:
        example_path = examples_dir / example_name
        if example_path.exists():
            if test_example(example_path):
                passed += 1
            else:
                failed += 1
        # Skip non-existent files silently (they're not in the codebase)

    return passed, failed


def test_example(example_file):
    """Test a single example file."""
    try:
        # Use longer timeout for certain examples
        if example_file.name == "agent_graph.py":
            timeout = 120
        elif example_file.name == "database_error_handling.py":
            timeout = 60  # MongoDB connection attempts can take time
        else:
            timeout = 30

        # Set PYTHONPATH to include the project root
        env = os.environ.copy()
        project_root = Path(__file__).parent.parent
        pythonpath = env.get("PYTHONPATH", "")
        if pythonpath:
            env["PYTHONPATH"] = f"{project_root}:{pythonpath}"
        else:
            env["PYTHONPATH"] = str(project_root)

        # Run the example with a timeout
        result = subprocess.run(
            [sys.executable, str(example_file)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=Path(__file__).parent,
            env=env,
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
        # Set PYTHONPATH to include the project root
        env = os.environ.copy()
        project_root = Path(__file__).parent.parent
        pythonpath = env.get("PYTHONPATH", "")
        if pythonpath:
            env["PYTHONPATH"] = f"{project_root}:{pythonpath}"
        else:
            env["PYTHONPATH"] = str(project_root)

        # For server examples, we just check if they start without errors
        # and then terminate them after a few seconds
        process = subprocess.Popen(
            [sys.executable, str(example_file)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=Path(__file__).parent,
            env=env,
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
    """Test all example files.

    The test runner will:
    1. Run each example file and verify it executes without errors
    2. Handle special cases like server examples that need early termination
    3. Skip long-running examples that are meant to run indefinitely
    4. Provide detailed reporting of test results

    Return codes:
    0 - All tests passed (some may be skipped)
    1 - Some tests failed or no tests passed
    """
    print("🧪 Testing jvspatial example files...")
    print("=" * 50)

    examples_dir = Path(__file__).parent

    # Initialize counters
    passed = failed = skipped = 0

    # Error handling examples
    error_handling_examples = [
        "error_handling/basic_error_handling.py",
        "error_handling/database_error_handling.py",
        "error_handling/walker_error_handling.py",
    ]

    # Updated examples with new walker patterns
    updated_examples = [
        "core/models/travel_graph.py",
        "core/context/graphcontext_demo.py",
        "core/models/agent_graph.py",
        "walkers/multi_target_hooks_demo.py",
    ]

    # Core examples
    core_examples = [
        "walkers/walker_traversal_demo.py",
        "database/filtering/enhanced_nodes_filtering.py",
        "database/query_interface_example.py",
        "database/pagination/object_pagination_demo.py",
        "database/filtering/semantic_filtering.py",
        "database/unified_query_interface_example.py",
        "database/custom_database_example.py",
        "database/database_switching_example.py",
        "walkers/walker_events_demo.py",
        "walkers/walker_reporting_demo.py",
    ]

    # Scheduler examples (long-running, skipped)
    scheduler_examples = [
        "scheduler/scheduler_example.py",  # Basic scheduler patterns
        "scheduler/dynamic_scheduler_demo.py",  # Advanced scheduler features
    ]

    # Storage examples (these start servers, so test as server examples)
    storage_examples = [
        "storage/storage_example.py",  # Comprehensive storage example
        "storage/file_storage_demo.py",  # File storage operations demo
    ]

    # API examples
    api_examples = [
        "api/authenticated_endpoints_example.py",  # Authenticated API endpoints
        "api/unauthenticated_endpoints_example.py",  # Unauthenticated API endpoints
    ]

    # Long-running examples to skip
    long_running_examples = [
        *scheduler_examples,
    ]

    # Run test groups
    group_passed, group_failed = run_example_group(
        examples_dir,
        error_handling_examples,
        "🛡️  Error Handling Examples:",
        "Examples demonstrating error handling patterns",
    )
    passed += group_passed
    failed += group_failed

    group_passed, group_failed = run_example_group(
        examples_dir,
        updated_examples,
        "✨ Updated Examples (New Walker Patterns):",
        "These examples have been updated to use report() pattern",
    )
    passed += group_passed
    failed += group_failed

    group_passed, group_failed = run_example_group(
        examples_dir, core_examples, "📊 Core Examples:", "Core functionality examples"
    )
    passed += group_passed
    failed += group_failed

    # Test storage examples (these start servers)
    print("\n🌐 Server Examples:")
    print("-" * 50)
    print("These start servers; we validate they start without errors")
    print()

    for example_name in storage_examples:
        example_path = examples_dir / example_name
        if example_path.exists():
            if test_server_example(example_path):
                passed += 1
            else:
                failed += 1
        else:
            print(f"❓ {example_name} (not found)")
            failed += 1

    # Test API examples
    group_passed, group_failed = run_example_group(
        examples_dir,
        api_examples,
        "\n🌐 API Examples:",
        "Examples demonstrating API endpoint patterns",
    )
    passed += group_passed
    failed += group_failed

    # Report long-running examples
    print("\n⏱️  Long Running Examples:")
    print("-" * 50)
    print("These run indefinitely (servers, schedulers)")
    print()

    for example_name in long_running_examples:
        example_path = examples_dir / example_name
        if example_path.exists():
            print(f"⏭️  {example_name} (skipped - runs indefinitely)")
            skipped += 1

    # Print summary
    print("\n" + "=" * 50)
    print("📈 Test Summary:")
    print("=" * 50)
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"⏭️  Skipped: {skipped}")
    print(f"📊 Total Tested: {passed + failed}")
    print(f"📦 Total Examples: {passed + failed + skipped}")

    if failed == 0 and passed > 0:
        print("\n🎉 All tested examples are working correctly!")
        if skipped > 0:
            print(f"ℹ️  {skipped} examples were skipped (long-running)")
        return 0
    elif passed == 0:
        print("\n⚠️  No examples were tested successfully")
        return 1
    else:
        print(f"\n⚠️  {failed} examples have issues")
        if skipped > 0:
            print(f"ℹ️  {skipped} examples were skipped")
        return 1


if __name__ == "__main__":
    sys.exit(main())
