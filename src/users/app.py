"""CRUD handler for the Users Service.

Routes API Gateway REST (v1) proxy events by httpMethod and resource:

    GET    /users            list all users
    POST   /users            create a user
    GET    /users/{userid}   fetch one user
    PUT    /users/{userid}   replace name and email
    DELETE /users/{userid}   remove a user
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

# The runtime attaches its JSON handler to the root logger, so no basicConfig, no
# added handler, and no setLevel: the level comes from application_log_level.
logger = logging.getLogger()
logging.getLogger("botocore").setLevel(logging.WARNING)

# The client interface is deliberate. boto3's resource interface lazy-loads Table
# attributes via DescribeTable, which this function's least-privilege policy does
# not grant, and that failure would only ever show up in deployed 500s.
dynamodb = boto3.client("dynamodb")
TABLE_NAME = os.environ["TABLE_NAME"]

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
}


class ValidationError(Exception):
    """Client sent something unusable; maps to 400."""


class NotFoundError(Exception):
    """No record for the requested userid; maps to 404."""


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json", **CORS_HEADERS},
        "body": json.dumps(body),
    }


def _now():
    return datetime.now(timezone.utc).isoformat()


def _to_item(record):
    """Every field in a user record is a string, so typing is this simple."""
    return {key: {"S": value} for key, value in record.items()}


def _from_item(item):
    return {key: value["S"] for key, value in item.items()}


def _parse_body(event):
    try:
        parsed = json.loads(event.get("body") or "")
    except (TypeError, ValueError):
        raise ValidationError("Request body must be valid JSON")
    if not isinstance(parsed, dict):
        raise ValidationError("Request body must be a JSON object")
    return parsed


def _required_fields(body):
    """Pull name and email, ignoring any client-supplied userid or timestamps."""
    fields = {}
    for field in ("name", "email"):
        value = body.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValidationError(
                f"Field '{field}' is required and must be a non-empty string"
            )
        fields[field] = value.strip()
    return fields


def create_user(body):
    fields = _required_fields(body)
    timestamp = _now()
    record = {
        "userid": str(uuid.uuid4()),
        **fields,
        "createdAt": timestamp,
        "updatedAt": timestamp,
    }
    dynamodb.put_item(
        TableName=TABLE_NAME,
        Item=_to_item(record),
        ConditionExpression="attribute_not_exists(userid)",
    )
    logger.info("created user", extra={"userid": record["userid"]})
    return _response(201, record)


def list_users():
    users = []
    start_key = None
    while True:
        kwargs = {"TableName": TABLE_NAME}
        if start_key:
            kwargs["ExclusiveStartKey"] = start_key
        page = dynamodb.scan(**kwargs)
        users.extend(_from_item(item) for item in page.get("Items", []))
        start_key = page.get("LastEvaluatedKey")
        if not start_key:
            break
    logger.info("listed users", extra={"count": len(users)})
    return _response(200, {"users": users, "count": len(users)})


def get_user(userid):
    item = dynamodb.get_item(
        TableName=TABLE_NAME,
        Key={"userid": {"S": userid}},
    ).get("Item")
    if not item:
        raise NotFoundError
    return _response(200, _from_item(item))


def update_user(userid, body):
    fields = _required_fields(body)
    try:
        updated = dynamodb.update_item(
            TableName=TABLE_NAME,
            Key={"userid": {"S": userid}},
            # name is a DynamoDB reserved word, hence the attribute name aliases.
            UpdateExpression="SET #name = :name, #email = :email, #updatedAt = :updatedAt",
            ExpressionAttributeNames={
                "#name": "name",
                "#email": "email",
                "#updatedAt": "updatedAt",
            },
            ExpressionAttributeValues={
                ":name": {"S": fields["name"]},
                ":email": {"S": fields["email"]},
                ":updatedAt": {"S": _now()},
            },
            ConditionExpression="attribute_exists(userid)",
            ReturnValues="ALL_NEW",
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise NotFoundError from exc
        raise
    logger.info("updated user", extra={"userid": userid})
    return _response(200, _from_item(updated["Attributes"]))


def delete_user(userid):
    try:
        dynamodb.delete_item(
            TableName=TABLE_NAME,
            Key={"userid": {"S": userid}},
            ConditionExpression="attribute_exists(userid)",
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise NotFoundError from exc
        raise
    logger.info("deleted user", extra={"userid": userid})
    return _response(200, {})


def lambda_handler(event, context):
    method = event.get("httpMethod")
    # resource is the literal route template, never the expanded path.
    resource = event.get("resource")
    userid = (event.get("pathParameters") or {}).get("userid")
    logger.info(
        "request received",
        extra={"method": method, "resource": resource, "userid": userid},
    )

    try:
        if resource == "/users":
            if method == "GET":
                return list_users()
            if method == "POST":
                return create_user(_parse_body(event))
        elif resource == "/users/{userid}":
            if method == "GET":
                return get_user(userid)
            if method == "PUT":
                return update_user(userid, _parse_body(event))
            if method == "DELETE":
                return delete_user(userid)
        return _response(404, {"message": "Not found"})
    except ValidationError as exc:
        logger.info("validation failed", extra={"reason": str(exc)})
        return _response(400, {"message": str(exc)})
    except NotFoundError:
        logger.info("user not found", extra={"userid": userid})
        return _response(404, {"message": "User not found"})
    except ClientError:
        # Details go to the log; the client gets a generic message.
        logger.error("dynamodb call failed", exc_info=True, extra={"table": TABLE_NAME})
        return _response(500, {"message": "Internal server error"})
