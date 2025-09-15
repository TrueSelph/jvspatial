"""Factory function for database instances."""

import os

from .database import Database
from .jsondb import JsonDB
from .mongodb import MongoDB


def get_database() -> Database:
    """Get the configured database instance."""
    db_type = os.getenv("JVSPATIAL_DB_TYPE", "json")

    if db_type == "mongodb":
        return MongoDB()
    elif db_type == "json":
        db_path = os.getenv("JVSPATIAL_JSONDB_PATH", "jvdb")
        return JsonDB(db_path)
    else:
        raise ValueError(f"Unsupported database type: {db_type}")
