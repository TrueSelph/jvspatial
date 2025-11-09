"""Basic Error Handling Example

Demonstrates fundamental error handling patterns in jvspatial, including:
- Entity operation errors
- Validation errors
- General error handling patterns
"""

import asyncio
from datetime import datetime
from typing import Optional

from pydantic import EmailStr, Field
from pydantic import ValidationError as PydanticValidationError

from jvspatial.core import Node
from jvspatial.exceptions import (
    EntityNotFoundError,
    JVSpatialError,
)


# Define example entities
class User(Node):
    """User entity with validation rules."""

    name: str = Field(..., min_length=2)
    email: EmailStr
    age: int = Field(..., ge=0, le=150)
    created_at: datetime = Field(default_factory=datetime.now)
    last_login: Optional[datetime] = None


async def demonstrate_entity_errors():
    """Demonstrate handling of entity-related errors."""
    print("\n🔍 Demonstrating entity error handling:")

    try:
        # Try to create user with invalid data
        user = await User.create(
            name="A",  # Too short
            email="invalid-email",  # Invalid email
            age=200,  # Age out of range
        )
    except PydanticValidationError as e:
        print(f"❌ Validation failed: {e}")
        # Pydantic ValidationError has errors() method that returns list of errors
        for error in e.errors():
            field = ".".join(str(loc) for loc in error.get("loc", []))
            message = error.get("msg", "Validation error")
            print(f"  • {field}: {message}")

    try:
        # Try to fetch non-existent user
        # Note: Object.get() returns None if not found, doesn't raise exception
        user = await User.get("non_existent_id")
        if user is None:
            raise EntityNotFoundError(
                entity_type="User",
                entity_id="non_existent_id",
                details={"message": "User not found in database"},
            )
    except EntityNotFoundError as e:
        print(f"\n❌ Entity not found: {e.message}")
        print(f"  • Entity type: {e.entity_type}")
        print(f"  • Entity ID: {e.entity_id}")


async def demonstrate_successful_operations():
    """Demonstrate successful operations for comparison."""
    print("\n✨ Demonstrating successful operations:")

    try:
        # Create valid user
        user = await User.create(
            name="Alice Smith",
            email="alice.smith@example.com",
            age=30,
        )
        print(f"✅ Created user: {user.name} (ID: {user.id})")

        # Fetch existing user
        retrieved = await User.get(user.id)
        print(f"✅ Retrieved user: {retrieved.name}")

        # Update user
        retrieved.last_login = datetime.now()
        await retrieved.save()
        print(f"✅ Updated user last login")

    except JVSpatialError as e:
        print(f"❌ Unexpected jvspatial error: {e.message}")
        if e.details:
            print(f"Details: {e.details}")


async def main():
    """Run error handling demonstrations."""
    print("🚀 Basic Error Handling Example")
    print("===============================")

    try:
        await demonstrate_entity_errors()
        await demonstrate_successful_operations()

    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")

    print("\n✨ Example completed!")


if __name__ == "__main__":
    asyncio.run(main())
