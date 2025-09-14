import os
from .database import Database
from .mongodb import MongoDB
from .jsondb import JsonDB


def get_database() -> Database:
    db_type = os.getenv("JVSPATIAL_DB_TYPE", "json")

    if db_type == "mongodb":
        return MongoDB()
    elif db_type == "json":
        db_path = os.getenv("JVSPATIAL_JSONDB_PATH", "db/json")
        return JsonDB(db_path)
    else:
        raise ValueError(f"Unsupported database type: {db_type}")
