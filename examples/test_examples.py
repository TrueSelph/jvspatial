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
        # Use longer timeout for certain examples
        timeout = 60 if example_file.name == "agent_graph.py" else 30

        # Run the example with a timeout
        result = subprocess.run(
            [sys.executable, str(example_file)],
            capture_output=True,
            text=True,
            timeout=timeout,
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

    # Updated examples with new walker patterns (priority testing)
    updated_examples = [
        "core/models/travel_graph.py",
        "core/context/graphcontext_demo.py",
        "testing/testing_with_graphcontext.py",
        "core/models/agent_graph.py",
        "walkers/multi_target_hooks_demo.py",
    ]

    # Other core examples to test
    core_examples = [
        "database/crud_demo.py",
        "database/orm_demo.py",
        "walkers/walker_traversal_demo.py",
        "database/filtering/enhanced_nodes_filtering.py",
        "database/modern_query_interface.py",
        "database/pagination/object_pagination_demo.py",
        "walkers/traversal_demo.py",
        "database/filtering/semantic_filtering.py",
        "database/unified_query_interface_example.py",
        "database/custom_database_example.py",
        "database/custom_database_registry_example.py",
        "database/database_switching_example.py",
        "walkers/walker_events_demo.py",
        "walkers/walker_reporting_demo.py",
        "api/exception_handling_demo.py",
    ]

    # Server examples (in server/ directory)
    server_examples = [
        "server/comprehensive_server_example.py",  # Combined best practices
        "server/server_example.py",  # Basic patterns
        "server/server_demo.py",  # Advanced patterns
        "server/fastapi_server.py",  # FastAPI integration
        "server/dynamic_server_demo.py",  # Dynamic endpoint management
        "server/dynamic_endpoint_removal.py",  # Dynamic endpoint lifecycle
        "server/endpoint_decorator_demo.py",  # Decorator patterns
        "server/endpoint_respond_demo.py",  # Response patterns
        "server/exception_handling_demo.py",  # Error handling patterns
        "server/webhook_examples.py",  # Webhook patterns
    ]

    # Scheduler examples (in scheduler/ directory)
    scheduler_examples = [
        "scheduler/scheduler_example.py"  # Complete scheduler patterns
    ]

    # Authentication examples (in auth/ directory)
    auth_examples = [
        "auth/auth_demo.py",  # Authentication patterns
    ]

    # Long-running examples to skip (servers that don't exit on their own)
    long_running_examples = [
        *auth_examples,
        *scheduler_examples,
    ]

    passed = 0
    failed = 0
    skipped = 0

    print("\n✨ Updated Examples (New Walker Patterns):")
    print("-" * 50)
    print("These examples have been updated to use report() pattern")
    print()

    for example_name in updated_examples:
        example_path = examples_dir / example_name
        if example_path.exists():
            if test_example(example_path):
                passed += 1
            else:
                failed += 1
        else:
            print(f"❓ {example_name} (not found)")
            failed += 1

    print(f"\n📊 Core Examples:")
    print("-" * 30)

    for example_name in core_examples:
        example_path = examples_dir / example_name
        if example_path.exists():
            if test_example(example_path):
                passed += 1
            else:
                failed += 1
        else:
            print(f"⏭️  {example_name} (not found)")
            skipped += 1

    print(f"\n🌐 Server Examples:")
    print("-" * 50)
    print("These start servers; we validate they start without errors")
    print()

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

    print(f"\n⏱️  Long Running Examples:")
    print("-" * 50)
    print("These run indefinitely (servers, schedulers)")
    print()

    for example_name in long_running_examples:
        example_path = examples_dir / example_name
        if example_path.exists():
            print(f"⏭️  {example_name} (skipped - runs indefinitely)")
            skipped += 1
        else:
            print(f"❓ {example_name} (not found)")
            skipped += 1

    print(f"\n" + "=" * 50)
    print(f"📈 Test Summary:")
    print(f"=" * 50)
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"⏭️  Skipped: {skipped}")
    print(f"📊 Total Tested: {passed + failed}")
    print(f"📦 Total Examples: {passed + failed + skipped}")

    if failed == 0 and passed > 0:
        print("\n🎉 All tested examples are working correctly!")
        if skipped > 0:
            print(f"ℹ️  {skipped} examples were skipped (need updates or not found)")
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
