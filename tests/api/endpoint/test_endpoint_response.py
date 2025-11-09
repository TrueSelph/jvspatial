"""Unit tests for the EndpointResponse class and response utilities."""

import pytest
from fastapi.responses import JSONResponse

from jvspatial.api.endpoints.response import EndpointResponse
from jvspatial.api.endpoints.response import ResponseHelper as EndpointResponseHelper
from jvspatial.api.endpoints.response import create_endpoint_helper


class TestEndpointResponse:
    """Test cases for EndpointResponse class."""

    async def test_endpoint_response_init(self):
        """Test EndpointResponse initialization with default values."""
        response = EndpointResponse()

        assert response.content is None
        assert response.status_code == 200
        assert response.headers == {}
        assert response.media_type == "application/json"

    async def test_endpoint_response_init_with_values(self):
        """Test EndpointResponse initialization with custom values."""
        content = {"data": "test"}
        headers = {"X-Custom": "value"}

        response = EndpointResponse(
            content=content,
            status_code=201,
            headers=headers,
            media_type="application/custom",
        )

        assert response.content == content
        assert response.status_code == 201
        assert response.headers == headers
        assert response.media_type == "application/custom"

    async def test_to_json_response(self):
        """Test conversion to FastAPI JSONResponse."""
        content = {"message": "success", "data": {"id": 123}}
        headers = {"X-Custom": "header"}

        response = EndpointResponse(content=content, status_code=201, headers=headers)

        json_response = await response.to_json_response()

        assert isinstance(json_response, JSONResponse)
        # Note: JSONResponse properties are not directly accessible,
        # but we can verify the type and that it was created without errors

    async def test_to_dict_simple(self):
        """Test conversion to dictionary with simple content."""
        content = {"message": "success", "id": 123}

        response = EndpointResponse(content=content, status_code=201)

        result = await response.to_dict()

        expected = {"status": 201, "message": "success", "id": 123}

        assert result == expected

    async def test_to_dict_with_data_field(self):
        """Test conversion to dictionary with non-dict content."""
        content = "simple string content"

        response = EndpointResponse(content=content, status_code=200)

        result = await response.to_dict()

        expected = {"status": 200, "data": "simple string content"}

        assert result == expected

    async def test_to_dict_with_headers(self):
        """Test conversion to dictionary with headers."""
        content = {"message": "success"}
        headers = {"X-Custom": "value", "X-Another": "test"}

        response = EndpointResponse(content=content, status_code=200, headers=headers)

        result = await response.to_dict()

        expected = {
            "status": 200,
            "message": "success",
            "headers": {"X-Custom": "value", "X-Another": "test"},
        }

        assert result == expected

    async def test_to_dict_none_content(self):
        """Test conversion to dictionary with None content."""
        response = EndpointResponse(content=None, status_code=204)

        result = await response.to_dict()

        expected = {"status": 204}

        assert result == expected

    async def test_to_dict_empty_dict_content(self):
        """Test conversion to dictionary with empty dict content."""
        response = EndpointResponse(content={}, status_code=200)

        result = await response.to_dict()

        expected = {"status": 200}

        assert result == expected

    async def test_to_dict_complex_content(self):
        """Test conversion with complex nested content."""
        content = {
            "data": {
                "user": {"id": 1, "name": "Alice"},
                "settings": {"theme": "dark", "notifications": True},
            },
            "meta": {"timestamp": "2025-09-21T06:32:18Z", "version": "1.0.0"},
        }

        response = EndpointResponse(
            content=content, status_code=200, headers={"X-Version": "1.0.0"}
        )

        result = await response.to_dict()

        expected = {
            "status": 200,
            "data": {
                "user": {"id": 1, "name": "Alice"},
                "settings": {"theme": "dark", "notifications": True},
            },
            "meta": {"timestamp": "2025-09-21T06:32:18Z", "version": "1.0.0"},
            "headers": {"X-Version": "1.0.0"},
        }

        assert result == expected


class TestEndpointResponseHelper:
    """Test cases for EndpointResponseHelper class."""

    async def test_helper_init_without_walker(self):
        """Test helper initialization without walker instance."""
        helper = EndpointResponseHelper()

        assert helper.walker_instance is None

    async def test_helper_init_with_walker(self):
        """Test helper initialization with walker instance."""
        mock_walker = type("MockWalker", (), {})()
        helper = EndpointResponseHelper(walker_instance=mock_walker)

        assert helper.walker_instance is mock_walker

    async def test_response_method_with_walker(self):
        """Test response method with walker instance."""
        mock_walker = type("MockWalker", (), {"response": None})()
        helper = EndpointResponseHelper(walker_instance=mock_walker)

        result = await helper.response(
            content={"message": "test"}, status_code=201, headers={"X-Custom": "value"}
        )

        # Should update walker response property
        assert mock_walker.response is not None
        assert mock_walker.response["status"] == 201
        assert mock_walker.response["message"] == "test"
        assert mock_walker.response["headers"]["X-Custom"] == "value"

        # Should return dict for walker
        assert isinstance(result, dict)
        assert result == mock_walker.response

    async def test_response_method_without_walker(self):
        """Test response method without walker instance."""
        helper = EndpointResponseHelper()

        result = await helper.response(
            content={"message": "test"}, status_code=201, headers={"X-Custom": "value"}
        )

        # Should return JSONResponse for function endpoints
        assert isinstance(result, JSONResponse)

    async def test_success_method_with_data(self):
        """Test success method with data."""
        mock_walker = type("MockWalker", (), {"response": None})()
        helper = EndpointResponseHelper(walker_instance=mock_walker)

        result = await helper.success(
            data={"id": 123, "name": "Alice"}, message="User retrieved successfully"
        )

        assert mock_walker.response["status"] == 200
        assert mock_walker.response["data"]["id"] == 123
        assert mock_walker.response["data"]["name"] == "Alice"
        assert mock_walker.response["message"] == "User retrieved successfully"

    async def test_success_method_without_data(self):
        """Test success method without data, only message."""
        mock_walker = type("MockWalker", (), {"response": None})()
        helper = EndpointResponseHelper(walker_instance=mock_walker)

        result = await helper.success(message="Operation completed")

        assert mock_walker.response["status"] == 200
        assert mock_walker.response["message"] == "Operation completed"
        assert "data" not in mock_walker.response

    async def test_created_method(self):
        """Test created method."""
        mock_walker = type("MockWalker", (), {"response": None})()
        helper = EndpointResponseHelper(walker_instance=mock_walker)

        result = await helper.created(
            data={"id": "user_123"},
            message="User created",
            headers={"Location": "/users/123"},
        )

        assert mock_walker.response["status"] == 201
        assert mock_walker.response["data"]["id"] == "user_123"
        assert mock_walker.response["message"] == "User created"
        assert mock_walker.response["headers"]["Location"] == "/users/123"

    async def test_no_content_method(self):
        """Test no_content method."""
        mock_walker = type("MockWalker", (), {"response": None})()
        helper = EndpointResponseHelper(walker_instance=mock_walker)

        result = await helper.no_content(headers={"X-Deleted": "true"})

        assert mock_walker.response["status"] == 204
        assert mock_walker.response["headers"]["X-Deleted"] == "true"

    async def test_bad_request_method(self):
        """Test bad_request method."""
        mock_walker = type("MockWalker", (), {"response": None})()
        helper = EndpointResponseHelper(walker_instance=mock_walker)

        result = await helper.bad_request(
            message="Invalid input",
            details={"field": "email", "issue": "invalid format"},
        )

        assert mock_walker.response["status"] == 400
        assert mock_walker.response["error"] == "Invalid input"
        assert mock_walker.response["details"]["field"] == "email"
        assert mock_walker.response["details"]["issue"] == "invalid format"

    async def test_unauthorized_method(self):
        """Test unauthorized method."""
        mock_walker = type("MockWalker", (), {"response": None})()
        helper = EndpointResponseHelper(walker_instance=mock_walker)

        result = await helper.unauthorized(
            message="Authentication required", details={"auth_method": "bearer_token"}
        )

        assert mock_walker.response["status"] == 401
        assert mock_walker.response["error"] == "Authentication required"
        assert mock_walker.response["details"]["auth_method"] == "bearer_token"

    async def test_forbidden_method(self):
        """Test forbidden method."""
        helper = EndpointResponseHelper()

        result = await helper.forbidden(
            message="Access denied", details={"required_role": "admin"}
        )

        # Should return JSONResponse since no walker instance
        assert isinstance(result, JSONResponse)

    async def test_not_found_method(self):
        """Test not_found method."""
        mock_walker = type("MockWalker", (), {"response": None})()
        helper = EndpointResponseHelper(walker_instance=mock_walker)

        result = await helper.not_found(
            message="User not found", details={"user_id": "123"}
        )

        assert mock_walker.response["status"] == 404
        assert mock_walker.response["error"] == "User not found"
        assert mock_walker.response["details"]["user_id"] == "123"

    async def test_conflict_method(self):
        """Test conflict method."""
        mock_walker = type("MockWalker", (), {"response": None})()
        helper = EndpointResponseHelper(walker_instance=mock_walker)

        result = await helper.conflict(
            message="Username already exists", details={"username": "alice"}
        )

        assert mock_walker.response["status"] == 409
        assert mock_walker.response["error"] == "Username already exists"
        assert mock_walker.response["details"]["username"] == "alice"

    async def test_unprocessable_entity_method(self):
        """Test unprocessable_entity method."""
        mock_walker = type("MockWalker", (), {"response": None})()
        helper = EndpointResponseHelper(walker_instance=mock_walker)

        result = await helper.unprocessable_entity(
            message="Validation failed",
            details={"errors": ["email required", "name too short"]},
        )

        assert mock_walker.response["status"] == 422
        assert mock_walker.response["error"] == "Validation failed"
        assert mock_walker.response["details"]["errors"] == [
            "email required",
            "name too short",
        ]

    async def test_internal_server_error_method(self):
        """Test internal_server_error method."""
        mock_walker = type("MockWalker", (), {"response": None})()
        helper = EndpointResponseHelper(walker_instance=mock_walker)

        result = await helper.internal_server_error(
            message="Database connection failed",
            details={"error_code": "DB_CONNECTION_TIMEOUT"},
        )

        assert mock_walker.response["status"] == 500
        assert mock_walker.response["error"] == "Database connection failed"
        assert mock_walker.response["details"]["error_code"] == "DB_CONNECTION_TIMEOUT"

    async def test_error_method_custom_status(self):
        """Test error method with custom status code."""
        mock_walker = type("MockWalker", (), {"response": None})()
        helper = EndpointResponseHelper(walker_instance=mock_walker)

        result = await helper.error(
            message="I'm a teapot", status_code=418, details={"reason": "april_fools"}
        )

        assert mock_walker.response["status"] == 418
        assert mock_walker.response["error"] == "I'm a teapot"
        assert mock_walker.response["details"]["reason"] == "april_fools"

    async def test_default_messages(self):
        """Test methods with default messages."""
        mock_walker = type("MockWalker", (), {"response": None})()
        helper = EndpointResponseHelper(walker_instance=mock_walker)

        # Test default messages
        await helper.bad_request()
        assert mock_walker.response["error"] == "Bad Request"

        await helper.unauthorized()
        assert mock_walker.response["error"] == "Unauthorized"

        await helper.forbidden()
        assert mock_walker.response["error"] == "Forbidden"

        await helper.not_found()
        assert mock_walker.response["error"] == "Not Found"

        await helper.conflict()
        assert mock_walker.response["error"] == "Conflict"


class TestCreateEndpointHelper:
    """Test cases for create_endpoint_helper factory function."""

    async def test_create_helper_without_walker(self):
        """Test creating helper without walker instance."""
        helper = create_endpoint_helper()

        assert isinstance(helper, EndpointResponseHelper)
        assert helper.walker_instance is None

    async def test_create_helper_with_walker(self):
        """Test creating helper with walker instance."""
        mock_walker = type("MockWalker", (), {})()
        helper = create_endpoint_helper(walker_instance=mock_walker)

        assert isinstance(helper, EndpointResponseHelper)
        assert helper.walker_instance is mock_walker
