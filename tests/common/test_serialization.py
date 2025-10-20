"""Test suite for common serialization utilities."""

from datetime import datetime

import pytest

from jvspatial.common.serialization import deserialize_datetime, serialize_datetime


class TestSerializationUtilities:
    """Test serialization utility functions."""

    def test_serialize_datetime_basic(self):
        """Test serializing datetime."""
        dt = datetime(2023, 1, 1, 12, 0, 0)
        result = serialize_datetime(dt)
        assert result == "2023-01-01T12:00:00"

    def test_serialize_datetime_dict(self):
        """Test serializing datetime in dictionary."""
        dt = datetime(2023, 1, 1, 12, 0, 0)
        data = {"key": "value", "timestamp": dt}
        result = serialize_datetime(data)
        assert result["key"] == "value"
        assert result["timestamp"] == "2023-01-01T12:00:00"

    def test_serialize_datetime_list(self):
        """Test serializing datetime in list."""
        dt1 = datetime(2023, 1, 1, 12, 0, 0)
        dt2 = datetime(2023, 1, 2, 12, 0, 0)
        data = [dt1, dt2, "string"]
        result = serialize_datetime(data)
        assert result[0] == "2023-01-01T12:00:00"
        assert result[1] == "2023-01-02T12:00:00"
        assert result[2] == "string"

    def test_serialize_datetime_nested(self):
        """Test serializing datetime in nested structure."""
        dt = datetime(2023, 1, 1, 12, 0, 0)
        data = {"level1": {"level2": {"timestamp": dt, "value": "test"}}}
        result = serialize_datetime(data)
        assert result["level1"]["level2"]["timestamp"] == "2023-01-01T12:00:00"
        assert result["level1"]["level2"]["value"] == "test"

    def test_deserialize_datetime_basic(self):
        """Test deserializing datetime."""
        dt_str = "2023-01-01T12:00:00"
        result = deserialize_datetime(dt_str)
        assert isinstance(result, datetime)
        assert result.year == 2023
        assert result.month == 1
        assert result.day == 1

    def test_deserialize_datetime_dict(self):
        """Test deserializing datetime in dictionary."""
        data = {"key": "value", "timestamp": "2023-01-01T12:00:00"}
        result = deserialize_datetime(data)
        assert result["key"] == "value"
        assert isinstance(result["timestamp"], datetime)

    def test_deserialize_datetime_list(self):
        """Test deserializing datetime in list."""
        data = ["2023-01-01T12:00:00", "2023-01-02T12:00:00", "string"]
        result = deserialize_datetime(data)
        assert isinstance(result[0], datetime)
        assert isinstance(result[1], datetime)
        assert result[2] == "string"

    def test_deserialize_datetime_invalid(self):
        """Test deserializing invalid datetime string."""
        invalid_str = "not-a-datetime"
        result = deserialize_datetime(invalid_str)
        assert result == "not-a-datetime"  # Should return as-is

    def test_serialize_datetime_non_datetime(self):
        """Test serializing non-datetime objects."""
        data = {"key": "value", "number": 42}
        result = serialize_datetime(data)
        assert result == data  # Should return unchanged
