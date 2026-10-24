"""Unit tests for the CRUD Lambda function, against a moto-mocked table.

Requirement references are to specs/users-service/requirements.md.
"""

import json
import uuid

import pytest
from botocore.exceptions import ClientError

from conftest import TABLE_NAME

CORS_ORIGIN = "Access-Control-Allow-Origin"


def event(method, resource, *, userid=None, body=None, raw_body=None):
    """Build a minimal API Gateway REST proxy event."""
    return {
        "httpMethod": method,
        "resource": resource,
        "pathParameters": {"userid": userid} if userid else None,
        "body": raw_body if raw_body is not None else (json.dumps(body) if body else None),
    }


def invoke(module, *args, **kwargs):
    """Call the handler and return (status, parsed body, headers)."""
    response = module.lambda_handler(event(*args, **kwargs), None)
    return response["statusCode"], json.loads(response["body"]), response["headers"]


def create(module, name="Ada Lovelace", email="ada@example.com"):
    status, body, _ = invoke(module, "POST", "/users", body={"name": name, "email": email})
    assert status == 201
    return body


# --------------------------------------------------------------------------
# User Story 1 -- create. One test per acceptance criterion.
# --------------------------------------------------------------------------


def test_create_returns_201_with_complete_record(users_app, users_table):
    """AC 1.1: valid POST stores the record and returns 201 with every field."""
    status, body, headers = invoke(
        users_app, "POST", "/users", body={"name": "Ada Lovelace", "email": "ada@example.com"}
    )

    assert status == 201
    assert set(body) == {"userid", "name", "email", "createdAt", "updatedAt"}
    assert body["name"] == "Ada Lovelace"
    assert body["email"] == "ada@example.com"
    assert uuid.UUID(body["userid"]).version == 4
    assert headers[CORS_ORIGIN] == "*"

    stored = users_table.get_item(TableName=TABLE_NAME, Key={"userid": {"S": body["userid"]}})
    assert stored["Item"]["name"]["S"] == "Ada Lovelace"


@pytest.mark.parametrize(
    "payload,bad_field",
    [
        ({"email": "a@example.com"}, "name"),
        ({"name": "", "email": "a@example.com"}, "name"),
        ({"name": "   ", "email": "a@example.com"}, "name"),
        ({"name": 42, "email": "a@example.com"}, "name"),
        ({"name": None, "email": "a@example.com"}, "name"),
        ({"name": "Ada"}, "email"),
        ({"name": "Ada", "email": ""}, "email"),
        ({"name": "Ada", "email": "  "}, "email"),
        ({"name": "Ada", "email": ["a@example.com"]}, "email"),
    ],
)
def test_create_rejects_invalid_fields_and_writes_nothing(users_app, users_table, payload, bad_field):
    """AC 1.2: missing, empty, blank, or non-string name/email gives 400, no write."""
    status, body, headers = invoke(users_app, "POST", "/users", body=payload)

    assert status == 400
    assert bad_field in body["message"]
    assert headers[CORS_ORIGIN] == "*"
    assert users_table.scan(TableName=TABLE_NAME)["Count"] == 0


@pytest.mark.parametrize("raw", ["{not valid json", "", "null", "[1, 2]", '"a string"'])
def test_create_rejects_non_object_json_body(users_app, users_table, raw):
    """AC 1.3: a body that is not a JSON object gives 400 and writes nothing."""
    status, body, _ = invoke(users_app, "POST", "/users", raw_body=raw)

    assert status == 400
    assert "message" in body
    assert users_table.scan(TableName=TABLE_NAME)["Count"] == 0


def test_create_ignores_client_supplied_server_fields(users_app):
    """AC 1.4: client-supplied userid, createdAt, and updatedAt are ignored."""
    status, body, _ = invoke(
        users_app,
        "POST",
        "/users",
        body={
            "name": "Ada",
            "email": "ada@example.com",
            "userid": "client-chosen-id",
            "createdAt": "1999-01-01T00:00:00+00:00",
            "updatedAt": "1999-01-01T00:00:00+00:00",
        },
    )

    assert status == 201
    assert body["userid"] != "client-chosen-id"
    assert uuid.UUID(body["userid"]).version == 4
    assert not body["createdAt"].startswith("1999")
    assert not body["updatedAt"].startswith("1999")


def test_create_sets_identical_timestamps(users_app):
    """AC 1.5: createdAt and updatedAt hold the same value on create."""
    body = create(users_app)

    assert body["createdAt"] == body["updatedAt"]


def test_create_trims_surrounding_whitespace(users_app):
    body = create(users_app, name="  Ada Lovelace  ", email="  ada@example.com  ")

    assert body["name"] == "Ada Lovelace"
    assert body["email"] == "ada@example.com"


# --------------------------------------------------------------------------
# User Story 2 -- read
# --------------------------------------------------------------------------


def test_list_returns_empty_array_when_table_is_empty(users_app):
    """AC 2.2: an empty table gives 200 with an empty array, not a 404."""
    status, body, headers = invoke(users_app, "GET", "/users")

    assert status == 200
    assert body == {"users": [], "count": 0}
    assert headers[CORS_ORIGIN] == "*"


def test_list_returns_all_records_with_count(users_app):
    """AC 2.1: every stored record appears, with a matching count."""
    created = [create(users_app, name=f"User {n}", email=f"u{n}@example.com") for n in range(3)]

    status, body, _ = invoke(users_app, "GET", "/users")

    assert status == 200
    assert body["count"] == 3
    assert len(body["users"]) == 3
    assert {u["userid"] for u in body["users"]} == {c["userid"] for c in created}


def test_list_follows_scan_pagination(users_app, monkeypatch):
    """A Scan past 1MB returns LastEvaluatedKey; every page must be collected.

    moto will not produce a truncated Scan for a handful of small items, so the
    paging is driven directly.
    """
    pages = [
        {"Items": [{"userid": {"S": "a"}, "name": {"S": "A"}}], "LastEvaluatedKey": {"userid": {"S": "a"}}},
        {"Items": [{"userid": {"S": "b"}, "name": {"S": "B"}}]},
    ]
    seen_start_keys = []

    def fake_scan(**kwargs):
        seen_start_keys.append(kwargs.get("ExclusiveStartKey"))
        return pages[len(seen_start_keys) - 1]

    monkeypatch.setattr(users_app.dynamodb, "scan", fake_scan)

    status, body, _ = invoke(users_app, "GET", "/users")

    assert status == 200
    assert body["count"] == 2
    assert [u["userid"] for u in body["users"]] == ["a", "b"]
    # First call unpaged, second resumes from the key the first page returned.
    assert seen_start_keys == [None, {"userid": {"S": "a"}}]


def test_get_returns_the_single_record(users_app):
    """AC 2.3: fetching by userid returns that record, not a list."""
    created = create(users_app)

    status, body, headers = invoke(users_app, "GET", "/users/{userid}", userid=created["userid"])

    assert status == 200
    assert body == created
    assert headers[CORS_ORIGIN] == "*"


def test_get_unknown_userid_returns_404(users_app):
    """AC 2.4."""
    status, body, headers = invoke(users_app, "GET", "/users/{userid}", userid="no-such-user")

    assert status == 404
    assert body["message"] == "User not found"
    assert headers[CORS_ORIGIN] == "*"


# --------------------------------------------------------------------------
# User Story 3 -- update and delete
# --------------------------------------------------------------------------


def test_update_replaces_fields_and_preserves_created_at(users_app):
    """AC 3.1."""
    created = create(users_app)

    status, body, headers = invoke(
        users_app,
        "PUT",
        "/users/{userid}",
        userid=created["userid"],
        body={"name": "Ada King", "email": "ada.king@example.com"},
    )

    assert status == 200
    assert body["name"] == "Ada King"
    assert body["email"] == "ada.king@example.com"
    assert body["userid"] == created["userid"]
    assert body["createdAt"] == created["createdAt"]
    assert body["updatedAt"] >= created["updatedAt"]
    assert headers[CORS_ORIGIN] == "*"


@pytest.mark.parametrize(
    "payload", [{"email": "a@example.com"}, {"name": "", "email": "a@example.com"}, {"name": "Ada"}]
)
def test_update_rejects_invalid_fields_and_leaves_record_intact(users_app, payload):
    """AC 3.2: invalid input gives 400 and does not modify the record."""
    created = create(users_app)

    status, body, _ = invoke(users_app, "PUT", "/users/{userid}", userid=created["userid"], body=payload)

    assert status == 400
    assert "message" in body

    _, unchanged, _ = invoke(users_app, "GET", "/users/{userid}", userid=created["userid"])
    assert unchanged == created


def test_update_unknown_userid_returns_404_and_creates_nothing(users_app, users_table):
    """AC 3.3: no upsert -- a missing record is a 404."""
    status, body, _ = invoke(
        users_app,
        "PUT",
        "/users/{userid}",
        userid="no-such-user",
        body={"name": "Ada", "email": "ada@example.com"},
    )

    assert status == 404
    assert body["message"] == "User not found"
    assert users_table.scan(TableName=TABLE_NAME)["Count"] == 0


def test_delete_returns_200_with_empty_object(users_app, users_table):
    """AC 3.4."""
    created = create(users_app)

    status, body, headers = invoke(users_app, "DELETE", "/users/{userid}", userid=created["userid"])

    assert status == 200
    assert body == {}
    assert headers[CORS_ORIGIN] == "*"
    assert users_table.scan(TableName=TABLE_NAME)["Count"] == 0


def test_delete_unknown_userid_returns_404(users_app):
    """AC 3.5."""
    status, body, _ = invoke(users_app, "DELETE", "/users/{userid}", userid="no-such-user")

    assert status == 404
    assert body["message"] == "User not found"


def test_delete_is_not_idempotent_after_the_first_call(users_app):
    created = create(users_app)

    assert invoke(users_app, "DELETE", "/users/{userid}", userid=created["userid"])[0] == 200
    assert invoke(users_app, "DELETE", "/users/{userid}", userid=created["userid"])[0] == 404


# --------------------------------------------------------------------------
# Non-functional requirements: routing and error handling
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method,resource",
    [
        ("DELETE", "/users"),
        ("PUT", "/users"),
        ("PATCH", "/users"),
        ("POST", "/users/{userid}"),
        ("PATCH", "/users/{userid}"),
        ("GET", "/unknown"),
        (None, None),
    ],
)
def test_unsupported_route_returns_404(users_app, method, resource):
    """NFR 5: an unsupported method and path combination gives 404."""
    status, body, headers = invoke(users_app, method, resource, userid="abc")

    assert status == 404
    assert body["message"] == "Not found"
    assert headers[CORS_ORIGIN] == "*"


@pytest.mark.parametrize("operation", ["scan", "get_item", "put_item", "update_item", "delete_item"])
def test_dynamodb_failure_returns_generic_500(users_app, monkeypatch, operation):
    """NFR 4: a failed DynamoDB call gives a generic 500, details only in logs."""
    error = ClientError(
        {"Error": {"Code": "InternalServerError", "Message": "boom: sensitive detail"}}, operation
    )

    def explode(*args, **kwargs):
        raise error

    monkeypatch.setattr(users_app.dynamodb, operation, explode)

    calls = {
        "scan": ("GET", "/users", None),
        "get_item": ("GET", "/users/{userid}", "abc"),
        "put_item": ("POST", "/users", None),
        "update_item": ("PUT", "/users/{userid}", "abc"),
        "delete_item": ("DELETE", "/users/{userid}", "abc"),
    }
    method, resource, userid = calls[operation]
    status, body, headers = invoke(
        users_app, method, resource, userid=userid, body={"name": "Ada", "email": "a@example.com"}
    )

    assert status == 500
    assert body == {"message": "Internal server error"}
    assert "sensitive detail" not in json.dumps(body)
    assert headers[CORS_ORIGIN] == "*"


def test_every_response_carries_the_full_cors_header_set(users_app):
    """NFR 3: CORS headers on every response the function produces."""
    response = users_app.lambda_handler(event("GET", "/users"), None)

    assert response["headers"]["Access-Control-Allow-Origin"] == "*"
    assert "Authorization" in response["headers"]["Access-Control-Allow-Headers"]
    assert "DELETE" in response["headers"]["Access-Control-Allow-Methods"]
    assert response["headers"]["Content-Type"] == "application/json"


def test_conditional_put_prevents_silent_overwrite(users_app, users_table):
    """Create uses attribute_not_exists, so a uuid collision cannot clobber."""
    created = create(users_app)

    with pytest.raises(ClientError) as excinfo:
        users_app.dynamodb.put_item(
            TableName=TABLE_NAME,
            Item={"userid": {"S": created["userid"]}, "name": {"S": "Impostor"}},
            ConditionExpression="attribute_not_exists(userid)",
        )

    assert excinfo.value.response["Error"]["Code"] == "ConditionalCheckFailedException"
