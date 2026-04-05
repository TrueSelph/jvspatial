"""Tests for EventBridge validation in validate_server_config_requirements."""

import os
from unittest.mock import patch

import pytest

from jvspatial.api.config import ServerConfig
from jvspatial.env_adapter import validate_server_config_requirements


def _minimal_server_config() -> ServerConfig:
    return ServerConfig()


def test_validate_eventbridge_ok_explicit_lambda_arn():
    cfg = _minimal_server_config()
    with patch.dict(
        os.environ,
        {
            "JVSPATIAL_EVENTBRIDGE_SCHEDULER_ENABLED": "true",
            "JVSPATIAL_EVENTBRIDGE_ROLE_ARN": "arn:aws:iam::111122223333:role/scheduler",
            "JVSPATIAL_EVENTBRIDGE_LAMBDA_ARN": "arn:aws:lambda:us-east-1:111122223333:function:app",
            "JVSPATIAL_CACHE_BACKEND": "memory",
        },
        clear=False,
    ):
        validate_server_config_requirements(cfg)


def test_validate_eventbridge_ok_composed_lambda_arn():
    cfg = _minimal_server_config()
    with patch.dict(
        os.environ,
        {
            "JVSPATIAL_EVENTBRIDGE_SCHEDULER_ENABLED": "1",
            "JVSPATIAL_EVENTBRIDGE_ROLE_ARN": "arn:aws:iam::111122223333:role/scheduler",
            "AWS_LAMBDA_FUNCTION_NAME": "my-fn",
            "AWS_ACCOUNT_ID": "111122223333",
            "AWS_REGION": "us-east-2",
            "JVSPATIAL_CACHE_BACKEND": "memory",
        },
        clear=False,
    ):
        validate_server_config_requirements(cfg)


def test_validate_eventbridge_fails_without_resolvable_lambda():
    cfg = _minimal_server_config()
    with patch.dict(
        os.environ,
        {
            "JVSPATIAL_EVENTBRIDGE_SCHEDULER_ENABLED": "yes",
            "JVSPATIAL_EVENTBRIDGE_ROLE_ARN": "arn:aws:iam::111122223333:role/scheduler",
            "AWS_LAMBDA_FUNCTION_NAME": "my-fn",
            "JVSPATIAL_CACHE_BACKEND": "memory",
        },
        clear=False,
    ):
        with pytest.raises(ValueError, match="JVSPATIAL_EVENTBRIDGE_LAMBDA_ARN"):
            validate_server_config_requirements(cfg)


def test_validate_eventbridge_fails_malformed_role_arn():
    cfg = _minimal_server_config()
    with patch.dict(
        os.environ,
        {
            "JVSPATIAL_EVENTBRIDGE_SCHEDULER_ENABLED": "true",
            "JVSPATIAL_EVENTBRIDGE_ROLE_ARN": "not-a-role-arn",
            "JVSPATIAL_EVENTBRIDGE_LAMBDA_ARN": "arn:aws:lambda:us-east-1:1:function:f",
            "JVSPATIAL_CACHE_BACKEND": "memory",
        },
        clear=False,
    ):
        with pytest.raises(ValueError, match="JVSPATIAL_EVENTBRIDGE_ROLE_ARN"):
            validate_server_config_requirements(cfg)
