# Database Versioning Strategies

## JSONDB Implementation

### Versioning Approach
Implements optimistic concurrency control through version stamps:

1. **Initial Version**: Each document receives `_version` field starting at 1
```json
{
  "id": "n:City:123",
  "_version": 1,
  "name": "New City"
}
```

2. **Update Validation**: Updates only succeed if client version matches stored version
```python
async def save(self, collection: str, data: dict):
    current_version = data.get('_version', 1)
    # Check version match before applying update
```

3. **Atomic Increment**: Successful updates auto-increment the version
```python
if existing_doc['_version'] == current_version:
    data['_version'] = current_version + 1
    # Save updated document
else:
    raise VersionConflictError()
```

4. **Conflict Handling**: Failed updates return HTTP 409 status with details
```json
{
  "error": "VersionConflict",
  "message": "Document version 2 does not match current version 3",
  "current_version": 3
}
```

### Migration Requirements
1. Add version field to all existing documents
2. Update query logic to handle version checks
3. Implement conflict resolution workflows

## MongoDB Implementation
Uses atomic findOneAndUpdate operations for consistency:
```python
result = await coll.find_one_and_update(
    {"_version": data['_version']},
    {"$set": data, "$inc": {"_version": 1}},
    return_document=ReturnDocument.AFTER
)