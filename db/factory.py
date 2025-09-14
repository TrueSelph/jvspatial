import os
from jvspatial.db.database import Database
from jvspatial.db.mongodb import MongoDB
from jvspatial.db.jsondb import JsonDB


def get_database() -> Database:
    db_type = os.getenv("JVGRAPH_DB_TYPE", "json")

    if db_type == "mongodb":
        # Propagate JVGRAPH_DB_URI to MONGODB_URI if set
        jvspatial_db_uri = os.getenv("JVGRAPH_DB_URI")
        if jvspatial_db_uri:
            os.environ["MONGODB_URI"] = jvspatial_db_uri
        return MongoDB()
    elif db_type == "json":
        db_path = os.getenv("JVGRAPH_DB_PATH", "db/json")
        return JsonDB(db_path)
    else:
        raise ValueError(f"Unsupported database type: {db_type}")
