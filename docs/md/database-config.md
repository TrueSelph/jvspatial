# Database Configuration

## Supported Backends
### JSON (Default)
```bash
# .env configuration
JVSPATIAL_DB_TYPE=json
JVSPATIAL_JSONDB_PATH=./jvdb
```

File structure:
```
jvdb/
├── node/
│   ├── n:Root:root.json
│   └── ...
└── edge/
    └── ...
```

### MongoDB
```bash
JVSPATIAL_DB_TYPE=mongodb
JVSPATIAL_MONGODB_URI=mongodb://localhost:27017
JVSPATIAL_MONGODB_DB_NAME=jvspatial
```

### Custom Implementation
```python
from jvspatial.db.database import Database

class CustomDB(Database):
    async def save(self, collection: str, data: dict) -> dict:
        # Implementation
        return await self.client.insert_one(collection, data)

    async def get(self, collection: str, id: str) -> Optional[dict]:
        return await self.client.find_one(collection, {"id": id})
```

## Migration Between Backends
1. Export data from current backend:
```bash
python -m jvspatial.tools.export --format json --output migration.json
```

2. Update .env file with new configuration

3. Import data:
```bash
python -m jvspatial.tools.import --input migration.json
