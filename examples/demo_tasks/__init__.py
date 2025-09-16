"""
demo_tasks - Example package for jvspatial walkers

This package demonstrates how to create installable walker packages
that can be discovered and registered at runtime by jvspatial servers.

Usage:
    # This package will be automatically discovered by servers with
    # package discovery patterns including 'demo_*'

Package structure:
    demo_tasks/
        __init__.py      # This file - exports walkers
        walkers.py       # Walker implementations
        models.py        # Node models (optional)
"""

from .walkers import TaskBulkUpdater, TaskNotificationSender, TaskReportGenerator

# Export walkers for discovery
__all__ = ["TaskReportGenerator", "TaskBulkUpdater", "TaskNotificationSender"]

# Package metadata
__version__ = "1.0.0"
__description__ = "Task management walkers for jvspatial"
