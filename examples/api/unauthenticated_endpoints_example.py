"""Unauthenticated API Endpoints Example

This example demonstrates a simple public API using the @endpoint decorator
with retrieval and listing operations. No authentication is required,
and the server does NOT automatically register login/register/logout endpoints.

Usage:
    python unauthenticated_endpoints_example.py
    Then visit http://localhost:8000/docs to see the Swagger UI

Key Features:
- Public endpoints for reading data
- Simple retrieval operations (GET by ID)
- Listing operations with pagination
- No authentication required
- Response schemas with examples
- Real persistence using the graph database
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from jvspatial.api import Server, endpoint
from jvspatial.api.endpoints.response import (
    ResponseField,
    response_schema,
    success_response,
)
from jvspatial.core import Node
from jvspatial.core.pager import ObjectPager

# =============================================================================
# DATA MODELS
# =============================================================================


class ArticleNode(Node):
    """Article node in the graph database."""

    title: str = ""
    content: str = ""
    author: str = ""
    category: str = ""
    published_at: Optional[str] = None
    views: int = 0
    tags: List[str] = []


class BookNode(Node):
    """Book node in the graph database."""

    title: str = ""
    author: str = ""
    isbn: str = ""
    year: int = 0
    pages: int = 0
    genre: str = ""
    description: Optional[str] = None


# =============================================================================
# SERVER SETUP
# =============================================================================

# Create server WITHOUT authentication enabled
server = Server(
    title="Public API Example",
    description="Simple public API with retrieval and listing operations",
    version="1.0.0",
    host="127.0.0.1",
    port=8000,
    # Database configuration
    db_type="json",
    db_path="./jvdb",
    # Authentication is NOT enabled - no login/register/logout endpoints will be created
    auth_enabled=False,
)

# Server is automatically set as current server upon instantiation

# =============================================================================
# SYSTEM ENDPOINTS
# =============================================================================


@endpoint(
    "/health",
    methods=["GET"],
    response=success_response(
        data={
            "status": ResponseField(
                field_type=str,
                description="Health status of the service",
                example="healthy",
            ),
            "timestamp": ResponseField(
                field_type=str,
                description="Current timestamp",
                example="2024-01-01T00:00:00Z",
            ),
            "version": ResponseField(
                field_type=str, description="Service version", example="1.0.0"
            ),
        }
    ),
)
async def health_check() -> Dict[str, Any]:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0",
    }


# =============================================================================
# ARTICLE ENDPOINTS
# =============================================================================


@endpoint(
    "/articles",
    methods=["GET"],
    response=success_response(
        data={
            "articles": ResponseField(
                field_type=List[Dict[str, Any]],
                description="List of articles",
                example=[
                    {
                        "id": "1",
                        "title": "Getting Started with Python",
                        "author": "John Doe",
                        "category": "Tutorial",
                        "views": 150,
                    }
                ],
            ),
            "total": ResponseField(
                field_type=int, description="Total number of articles", example=100
            ),
            "page": ResponseField(
                field_type=int, description="Current page number", example=1
            ),
            "per_page": ResponseField(
                field_type=int, description="Items per page", example=10
            ),
            "total_pages": ResponseField(
                field_type=int, description="Total number of pages", example=10
            ),
            "has_next": ResponseField(
                field_type=bool,
                description="Whether there is a next page",
                example=True,
            ),
            "has_previous": ResponseField(
                field_type=bool,
                description="Whether there is a previous page",
                example=False,
            ),
            "previous_page": ResponseField(
                field_type=Optional[int],  # type: ignore[arg-type]
                description="Previous page number",
                example=None,
            ),
            "next_page": ResponseField(
                field_type=Optional[int],  # type: ignore[arg-type]
                description="Next page number",
                example=2,
            ),
        }
    ),
)
async def list_articles(
    page: int = 1, per_page: int = 10, category: Optional[str] = None
) -> Dict[str, Any]:
    """List articles with optional pagination and category filtering."""
    # Create pager for articles
    pager = ObjectPager(ArticleNode, page_size=per_page)

    # Build query filters
    query = {}
    if category:
        query["category"] = category

    # Get paginated results
    articles: List[Any] = await pager.get_page(page=page, additional_filters=query)

    # Export articles to dictionaries
    articles_list = [article.export() for article in articles]

    # Get pagination info from pager
    pagination_info = pager.to_dict()

    return {
        "articles": articles_list,
        "total": pagination_info["total_items"],
        "page": pagination_info["current_page"],
        "per_page": pagination_info["page_size"],
        "total_pages": pagination_info["total_pages"],
        "has_next": pagination_info["has_next"],
        "has_previous": pagination_info["has_previous"],
        "previous_page": pagination_info["previous_page"],
        "next_page": pagination_info["next_page"],
    }


@endpoint(
    "/articles/{article_id}",
    methods=["GET"],
    response=success_response(
        data={
            "article": ResponseField(
                field_type=Dict[str, Any],
                description="Article information",
                example={
                    "id": "1",
                    "title": "Getting Started with Python",
                    "content": "Python is a versatile programming language...",
                    "author": "John Doe",
                    "category": "Tutorial",
                    "views": 150,
                    "published_at": "2024-01-01T00:00:00Z",
                },
            )
        }
    ),
)
async def get_article(article_id: str) -> Dict[str, Any]:
    """Get a specific article by ID."""
    # Retrieve article using entity-centric approach
    article = await ArticleNode.get(article_id)
    if not article:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Article not found")

    return {"article": article.export()}


# =============================================================================
# BOOK ENDPOINTS
# =============================================================================


@endpoint(
    "/books",
    methods=["GET"],
    response=success_response(
        data={
            "books": ResponseField(
                field_type=List[Dict[str, Any]],
                description="List of books",
                example=[
                    {
                        "id": "1",
                        "title": "The Great Gatsby",
                        "author": "F. Scott Fitzgerald",
                        "year": 1925,
                        "genre": "Fiction",
                    }
                ],
            ),
            "total": ResponseField(
                field_type=int, description="Total number of books", example=50
            ),
            "page": ResponseField(
                field_type=int, description="Current page number", example=1
            ),
            "per_page": ResponseField(
                field_type=int, description="Items per page", example=10
            ),
            "total_pages": ResponseField(
                field_type=int, description="Total number of pages", example=5
            ),
            "has_next": ResponseField(
                field_type=bool,
                description="Whether there is a next page",
                example=True,
            ),
            "has_previous": ResponseField(
                field_type=bool,
                description="Whether there is a previous page",
                example=False,
            ),
            "previous_page": ResponseField(
                field_type=Optional[int],  # type: ignore[arg-type]
                description="Previous page number",
                example=None,
            ),
            "next_page": ResponseField(
                field_type=Optional[int],  # type: ignore[arg-type]
                description="Next page number",
                example=2,
            ),
        }
    ),
)
async def list_books(
    page: int = 1,
    per_page: int = 10,
    author: Optional[str] = None,
    genre: Optional[str] = None,
    year: Optional[int] = None,
) -> Dict[str, Any]:
    """List books with optional pagination and filtering."""
    # Create pager for books
    pager = ObjectPager(BookNode, page_size=per_page)

    # Build query filters
    query = {}
    if author:
        query["author"] = author
    if genre:
        query["genre"] = genre
    if year:
        query["year"] = year  # type: ignore[assignment]

    # Get paginated results
    books: List[Any] = await pager.get_page(page=page, additional_filters=query)

    # Export books to dictionaries
    books_list = [book.export() for book in books]

    # Get pagination info from pager
    pagination_info = pager.to_dict()

    return {
        "books": books_list,
        "total": pagination_info["total_items"],
        "page": pagination_info["current_page"],
        "per_page": pagination_info["page_size"],
        "total_pages": pagination_info["total_pages"],
        "has_next": pagination_info["has_next"],
        "has_previous": pagination_info["has_previous"],
        "previous_page": pagination_info["previous_page"],
        "next_page": pagination_info["next_page"],
    }


@endpoint(
    "/books/{book_id}",
    methods=["GET"],
    response=success_response(
        data={
            "book": ResponseField(
                field_type=Dict[str, Any],
                description="Book information",
                example={
                    "id": "1",
                    "title": "The Great Gatsby",
                    "author": "F. Scott Fitzgerald",
                    "isbn": "978-0-7432-7356-5",
                    "year": 1925,
                    "pages": 180,
                    "genre": "Fiction",
                    "description": "A classic American novel...",
                },
            )
        }
    ),
)
async def get_book(book_id: str) -> Dict[str, Any]:
    """Get a specific book by ID."""
    # Retrieve book using entity-centric approach
    book = await BookNode.get(book_id)
    if not book:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Book not found")

    return {"book": book.export()}


# =============================================================================
# STATISTICS ENDPOINT
# =============================================================================


@endpoint(
    "/stats",
    methods=["GET"],
    response=success_response(
        data={
            "total_articles": ResponseField(
                field_type=int,
                description="Total number of articles",
                example=100,
            ),
            "total_books": ResponseField(
                field_type=int, description="Total number of books", example=50
            ),
            "total_views": ResponseField(
                field_type=int,
                description="Total views across all articles",
                example=15000,
            ),
        }
    ),
)
async def get_stats() -> Dict[str, Any]:
    """Get statistics about the content."""
    # Get all articles and books
    articles = await ArticleNode.find()
    books = await BookNode.find()

    # Calculate total views
    total_views = sum(article.views for article in articles)

    return {
        "total_articles": len(articles),
        "total_books": len(books),
        "total_views": total_views,
    }


# =============================================================================
# MAIN EXECUTION
# =============================================================================

if __name__ == "__main__":
    print("=" * 80)
    print("Unauthenticated Public API Example with jvspatial")
    print("=" * 80)
    print(
        "This example demonstrates a simple public API with retrieval and listing operations."
    )
    print()
    print("Key Features:")
    print("  - Public endpoints (no authentication required)")
    print("  - Simple retrieval operations (GET by ID)")
    print("  - Listing operations with pagination")
    print("  - Response schemas with examples")
    print("  - Real persistence using the graph database")
    print()
    print("Endpoints:")
    print("  - GET  /health                    (system health check)")
    print("  - GET  /articles                  (list articles with pagination)")
    print("  - GET  /articles/{id}             (get article by ID)")
    print(
        "  - GET  /books                     (list books with pagination and filtering)"
    )
    print("  - GET  /books/{id}                (get book by ID)")
    print("  - GET  /stats                     (get content statistics)")
    print()
    print("Note: No authentication endpoints are registered")
    print("      (no /auth/register, /auth/login, /auth/logout)")
    print()
    print("Visit http://localhost:8000/docs to see the Swagger UI")
    print("=" * 80)

    # Start the server
    server.run()
