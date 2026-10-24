"""Shared fixtures for the Users Service unit tests.

Both Lambda entry points are named app.py. Importing them by module name would
make whichever loaded first shadow the other for the rest of the session, so
each is loaded by file path under its own module name instead.
"""

import importlib.util
import pathlib
import sys

import boto3
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from moto import mock_aws

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"

TABLE_NAME = "workshop-users-test"
USER_POOL_ID = "us-west-2_TESTPOOL1"
APP_CLIENT_ID = "testappclientid0000000000"
REGION = "us-west-2"
ISSUER = f"https://cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}"


def load_handler(module_name, relative_path):
    """Load a handler module from its path, under an explicit module name."""
    path = SRC_DIR / relative_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    # Registered before exec so that a module-level failure is still inspectable.
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def aws_credentials(monkeypatch):
    """Fake credentials, so a misconfigured mock can never reach real AWS."""
    for name, value in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SECURITY_TOKEN": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "AWS_DEFAULT_REGION": REGION,
        "AWS_REGION": REGION,
    }.items():
        monkeypatch.setenv(name, value)


@pytest.fixture
def users_table(aws_credentials, monkeypatch):
    """A mocked users table, matching the real table's key schema."""
    monkeypatch.setenv("TABLE_NAME", TABLE_NAME)
    with mock_aws():
        client = boto3.client("dynamodb", region_name=REGION)
        client.create_table(
            TableName=TABLE_NAME,
            KeySchema=[{"AttributeName": "userid", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "userid", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield client


@pytest.fixture
def users_app(users_table):
    """The CRUD handler, loaded inside the mock.

    The module builds its DynamoDB client at import time, so it has to be
    imported while mock_aws is active for that client to be intercepted.
    """
    return load_handler("users_app_under_test", "users/app.py")


@pytest.fixture(scope="session")
def signing_key():
    """An RSA key generated locally. No test ever contacts Cognito."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="session")
def other_signing_key():
    """A second key, for producing tokens with an untrusted signature."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


class StubJWKClient:
    """Stands in for PyJWKClient, returning a fixed local public key.

    This is what keeps the authorizer tests offline: the real client would fetch
    the JWKS over HTTPS from the Cognito user pool.
    """

    def __init__(self, public_key):
        self._public_key = public_key
        self.calls = 0

    def get_signing_key_from_jwt(self, token):
        self.calls += 1
        return type("StubSigningKey", (), {"key": self._public_key})()


@pytest.fixture
def authorizer_app(monkeypatch, signing_key):
    """The authorizer handler with its JWKS client replaced by a local stub."""
    monkeypatch.setenv("USER_POOL_ID", USER_POOL_ID)
    monkeypatch.setenv("APP_CLIENT_ID", APP_CLIENT_ID)
    monkeypatch.setenv("AWS_REGION", REGION)

    module = load_handler("authorizer_app_under_test", "authorizer/app.py")
    module._jwk_client = StubJWKClient(signing_key.public_key())
    return module
