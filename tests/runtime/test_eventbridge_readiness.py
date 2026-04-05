"""Unit tests for EventBridge prerequisite helpers."""

import os
from unittest.mock import patch

from jvspatial.runtime.eventbridge_readiness import (
    aws_region_from_environ,
    eventbridge_scheduler_prerequisites_met_from_environ,
    resolve_eventbridge_lambda_arn_from_values,
)


def test_resolve_lambda_arn_explicit():
    assert (
        resolve_eventbridge_lambda_arn_from_values(
            "arn:aws:lambda:us-east-1:1:function:x",
            "ignored",
            "us-west-2",
            "2",
        )
        == "arn:aws:lambda:us-east-1:1:function:x"
    )


def test_resolve_lambda_arn_composed():
    assert (
        resolve_eventbridge_lambda_arn_from_values(
            "",
            "my-fn",
            "eu-west-1",
            "999888777666",
        )
        == "arn:aws:lambda:eu-west-1:999888777666:function:my-fn"
    )


def test_resolve_lambda_arn_empty_without_account():
    assert resolve_eventbridge_lambda_arn_from_values("", "fn", "us-east-1", "") == ""


def test_prerequisites_met_from_environ():
    with patch.dict(
        os.environ,
        {
            "JVSPATIAL_EVENTBRIDGE_ROLE_ARN": "arn:aws:iam::1:role/r",
            "JVSPATIAL_EVENTBRIDGE_LAMBDA_ARN": "arn:aws:lambda:us-east-1:1:function:f",
        },
        clear=False,
    ):
        assert eventbridge_scheduler_prerequisites_met_from_environ() is True


def test_prerequisites_not_met_without_role():
    with patch.dict(
        os.environ,
        {
            "JVSPATIAL_EVENTBRIDGE_ROLE_ARN": "",
            "JVSPATIAL_EVENTBRIDGE_LAMBDA_ARN": "arn:aws:lambda:us-east-1:1:function:f",
        },
        clear=False,
    ):
        assert eventbridge_scheduler_prerequisites_met_from_environ() is False


def test_aws_region_from_environ_prefers_aws_region():
    with patch.dict(
        os.environ,
        {"AWS_REGION": "eu-central-1", "AWS_DEFAULT_REGION": "us-west-2"},
        clear=False,
    ):
        assert aws_region_from_environ() == "eu-central-1"


def test_aws_region_from_environ_falls_back_to_default_region():
    with patch.dict(
        os.environ,
        {"AWS_REGION": "", "AWS_DEFAULT_REGION": ""},
        clear=False,
    ):
        assert aws_region_from_environ() == "us-east-1"
