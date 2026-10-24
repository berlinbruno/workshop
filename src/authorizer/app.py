"""API Gateway TOKEN authorizer for the Users Service.

Accepts only Cognito *access* tokens issued for this app client. The signature is
verified against the user pool's JWKS, which is cached at module level so a warm
execution environment never refetches it.

API Gateway maps the outcome as follows:
  - raising Exception("Unauthorized") -> 401
  - returning a Deny policy           -> 403
  - a missing Authorization header     -> 401, without invoking this function
"""

import logging
import os
import re

import jwt
from jwt import PyJWKClient

logger = logging.getLogger()

# Matches an optional leading "Bearer" scheme. The word boundary keeps it from
# eating the start of a token that merely begins with those letters, and
# allowing zero trailing whitespace means a bare "Bearer " header reduces to an
# empty token (401) rather than being mistaken for a token named "Bearer" (403).
_BEARER_PREFIX = re.compile(r"^\s*bearer\b\s*", re.IGNORECASE)

USER_POOL_ID = os.environ["USER_POOL_ID"]
APP_CLIENT_ID = os.environ["APP_CLIENT_ID"]
# AWS_REGION is set by the Lambda runtime; never hardcode a region.
REGION = os.environ["AWS_REGION"]

ISSUER = f"https://cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}"
JWKS_URL = f"{ISSUER}/.well-known/jwks.json"

# Module-level: the signing keys are fetched on the first invocation of an
# execution environment and reused by every later invocation.
_jwk_client = PyJWKClient(JWKS_URL)


def _stage_wide_resource(method_arn):
    """Widen a method ARN to every method and path in the same stage.

    methodArn looks like:
        arn:aws:execute-api:<region>:<account>:<api-id>/<stage>/<VERB>/<path>

    API Gateway caches an authorizer result per token, so the policy it caches
    has to authorize any endpoint the caller might hit next, not just the one
    that triggered this invocation.
    """
    parts = method_arn.split("/")
    return "/".join([parts[0], parts[1], "*", "*"])


def _policy(effect, principal_id, method_arn):
    return {
        "principalId": principal_id,
        "policyDocument": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": "execute-api:Invoke",
                    "Effect": effect,
                    "Resource": _stage_wide_resource(method_arn),
                }
            ],
        },
    }


def _allow(principal_id, method_arn, context):
    document = _policy("Allow", principal_id, method_arn)
    document["context"] = context
    return document


def _deny(principal_id, method_arn):
    """A Deny policy, which API Gateway renders as 403.

    Distinct from raising Unauthorized, which renders as 401: a token that was
    presented and rejected is reported differently from no token at all.
    """
    return _policy("Deny", principal_id, method_arn)


def lambda_handler(event, context):
    raw_header = event.get("authorizationToken") or ""
    token = _BEARER_PREFIX.sub("", raw_header, count=1).strip()

    if not token:
        logger.info("no bearer token supplied")
        raise Exception("Unauthorized")

    try:
        signing_key = _jwk_client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=ISSUER,
            # Cognito access tokens carry client_id rather than aud, so audience
            # verification is off and client_id is checked explicitly below.
            # token_use and client_id are checked below rather than required
            # here, so each rejection reports a distinct reason.
            options={
                "verify_aud": False,
                "require": ["exp", "iat", "sub", "token_use"],
            },
        )
    except Exception as exc:
        # The reason is logged by type only; the token itself is never logged.
        logger.info("token verification failed", extra={"reason": type(exc).__name__})
        return _deny("unauthorized", event["methodArn"])

    if claims["token_use"] != "access":
        logger.info("rejected non-access token", extra={"tokenUse": claims["token_use"]})
        return _deny(claims["sub"], event["methodArn"])

    if claims.get("client_id") != APP_CLIENT_ID:
        logger.info("rejected token issued for another app client")
        return _deny(claims["sub"], event["methodArn"])

    logger.info("request authorized", extra={"sub": claims["sub"]})
    return _allow(
        claims["sub"],
        event["methodArn"],
        {"sub": claims["sub"], "client_id": claims["client_id"]},
    )
