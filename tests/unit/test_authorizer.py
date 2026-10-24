"""Unit tests for the Lambda TOKEN authorizer.

Every token here is signed locally with an RSA key generated in a fixture, and
the authorizer's JWKS client is replaced by a stub, so no test contacts Cognito
or makes any network call.

Requirement references are to specs/users-service/requirements.md.
"""

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from conftest import APP_CLIENT_ID, ISSUER

METHOD_ARN = "arn:aws:execute-api:us-west-2:053935842459:9l0afrk3uh/prod/GET/users"
STAGE_WIDE_ARN = "arn:aws:execute-api:us-west-2:053935842459:9l0afrk3uh/prod/*/*"
SUB = "b8b113a0-90b1-70e9-09c6-f86873f411ef"


def make_token(
    key,
    *,
    token_use="access",
    client_id=APP_CLIENT_ID,
    issuer=ISSUER,
    sub=SUB,
    lifetime_seconds=3600,
    include_client_id=True,
    extra_claims=None,
):
    """Mint a locally signed token shaped like a Cognito one."""
    now = datetime.now(tz=timezone.utc)
    claims = {
        "sub": sub,
        "iss": issuer,
        "iat": now - timedelta(seconds=10),
        "exp": now + timedelta(seconds=lifetime_seconds),
        "token_use": token_use,
    }
    if include_client_id:
        claims["client_id"] = client_id
    claims.update(extra_claims or {})
    return jwt.encode(claims, key, algorithm="RS256")


def auth_event(token, method_arn=METHOD_ARN):
    return {"type": "TOKEN", "authorizationToken": token, "methodArn": method_arn}


def effect_of(policy):
    return policy["policyDocument"]["Statement"][0]["Effect"]


def resource_of(policy):
    return policy["policyDocument"]["Statement"][0]["Resource"]


# --------------------------------------------------------------------------
# AC 4.5 / 4.6 -- a valid access token is allowed, stage-wide
# --------------------------------------------------------------------------


def test_valid_access_token_is_allowed(authorizer_app, signing_key):
    """AC 4.5: a valid access token authorizes the request."""
    policy = authorizer_app.lambda_handler(auth_event(f"Bearer {make_token(signing_key)}"), None)

    assert effect_of(policy) == "Allow"
    assert policy["principalId"] == SUB


def test_allow_policy_exposes_sub_and_client_id_as_context(authorizer_app, signing_key):
    """AC 4.5: sub and client_id are passed to the CRUD function."""
    policy = authorizer_app.lambda_handler(auth_event(f"Bearer {make_token(signing_key)}"), None)

    assert policy["context"] == {"sub": SUB, "client_id": APP_CLIENT_ID}


def test_policy_resource_covers_every_method_and_path_in_the_stage(authorizer_app, signing_key):
    """AC 4.6: the cached decision has to authorize any later endpoint."""
    policy = authorizer_app.lambda_handler(auth_event(make_token(signing_key)), None)

    assert resource_of(policy) == STAGE_WIDE_ARN
    assert resource_of(policy).endswith("/prod/*/*")
    assert policy["policyDocument"]["Statement"][0]["Action"] == "execute-api:Invoke"


@pytest.mark.parametrize(
    "method_arn,expected",
    [
        (
            "arn:aws:execute-api:us-west-2:053935842459:9l0afrk3uh/prod/DELETE/users/abc-123",
            "arn:aws:execute-api:us-west-2:053935842459:9l0afrk3uh/prod/*/*",
        ),
        (
            "arn:aws:execute-api:eu-west-1:111122223333:otherapi/staging/POST/users",
            "arn:aws:execute-api:eu-west-1:111122223333:otherapi/staging/*/*",
        ),
    ],
)
def test_resource_widening_keeps_api_and_stage(authorizer_app, signing_key, method_arn, expected):
    """Only the verb and path are widened; api id and stage stay as they are."""
    policy = authorizer_app.lambda_handler(auth_event(make_token(signing_key), method_arn), None)

    assert resource_of(policy) == expected


@pytest.mark.parametrize("prefix", ["Bearer ", "bearer ", "BEARER ", ""])
def test_bearer_prefix_is_optional_and_case_insensitive(authorizer_app, signing_key, prefix):
    policy = authorizer_app.lambda_handler(auth_event(prefix + make_token(signing_key)), None)

    assert effect_of(policy) == "Allow"


# --------------------------------------------------------------------------
# AC 4.1 -- no token at all is a 401, which means raising
# --------------------------------------------------------------------------


@pytest.mark.parametrize("token", ["", "   ", "Bearer ", "Bearer", "bearer   ", None])
def test_absent_token_raises_unauthorized(authorizer_app, token):
    """AC 4.1: API Gateway renders this as 401, not 403.

    A scheme with nothing after it counts as no token, rather than as a token
    that happens to be the word "Bearer".
    """
    with pytest.raises(Exception, match="Unauthorized"):
        authorizer_app.lambda_handler(auth_event(token), None)


def test_token_beginning_with_bearer_letters_is_not_truncated(authorizer_app, signing_key):
    """Stripping the scheme must not eat the start of a real token."""
    token = make_token(signing_key)
    policy = authorizer_app.lambda_handler(auth_event("bearer" + token), None)

    # No separator, so this is one malformed token rather than scheme + token.
    assert effect_of(policy) == "Deny"


def test_absent_token_never_consults_the_jwks(authorizer_app):
    """No point fetching signing keys when there is nothing to verify."""
    with pytest.raises(Exception, match="Unauthorized"):
        authorizer_app.lambda_handler(auth_event(""), None)

    assert authorizer_app._jwk_client.calls == 0


# --------------------------------------------------------------------------
# AC 4.2 / 4.3 / 4.4 -- a token that is presented and rejected is a Deny, so 403
# --------------------------------------------------------------------------


def test_token_signed_by_another_key_is_denied(authorizer_app, other_signing_key):
    """AC 4.2: a signature that does not verify against the JWKS."""
    policy = authorizer_app.lambda_handler(auth_event(make_token(other_signing_key)), None)

    assert effect_of(policy) == "Deny"
    assert resource_of(policy) == STAGE_WIDE_ARN


def test_expired_token_is_denied(authorizer_app, signing_key):
    """AC 4.2: expiry is enforced."""
    policy = authorizer_app.lambda_handler(
        auth_event(make_token(signing_key, lifetime_seconds=-30)), None
    )

    assert effect_of(policy) == "Deny"


def test_token_from_another_issuer_is_denied(authorizer_app, signing_key):
    """AC 4.2: the issuer must be this user pool."""
    policy = authorizer_app.lambda_handler(
        auth_event(make_token(signing_key, issuer="https://cognito-idp.us-west-2.amazonaws.com/us-west-2_OTHER")),
        None,
    )

    assert effect_of(policy) == "Deny"


@pytest.mark.parametrize("garbage", ["not.a.jwt", "aaaa", "a.b.c", "Bearer x.y.z"])
def test_malformed_token_is_denied(authorizer_app, garbage):
    """AC 4.2: undecodable input is rejected rather than raising a 500."""
    policy = authorizer_app.lambda_handler(auth_event(garbage), None)

    assert effect_of(policy) == "Deny"
    assert policy["principalId"] == "unauthorized"


def test_id_token_is_denied(authorizer_app, signing_key):
    """AC 4.3: an ID token has token_use "id" and must not be accepted."""
    id_token = make_token(
        signing_key,
        token_use="id",
        include_client_id=False,
        extra_claims={"aud": APP_CLIENT_ID, "email": "tester@example.com"},
    )

    policy = authorizer_app.lambda_handler(auth_event(id_token), None)

    assert effect_of(policy) == "Deny"
    assert policy["principalId"] == SUB


def test_token_for_another_app_client_is_denied(authorizer_app, signing_key):
    """AC 4.4: client_id must match this app client."""
    policy = authorizer_app.lambda_handler(
        auth_event(make_token(signing_key, client_id="someotherappclient00000")), None
    )

    assert effect_of(policy) == "Deny"
    assert policy["principalId"] == SUB


def test_access_token_without_client_id_is_denied(authorizer_app, signing_key):
    """A token missing client_id entirely cannot match the app client."""
    policy = authorizer_app.lambda_handler(
        auth_event(make_token(signing_key, include_client_id=False)), None
    )

    assert effect_of(policy) == "Deny"


def test_token_missing_required_claims_is_denied(authorizer_app, signing_key):
    """token_use is required, so its absence is a rejection, not a KeyError."""
    now = datetime.now(tz=timezone.utc)
    incomplete = jwt.encode(
        {"sub": SUB, "iss": ISSUER, "iat": now, "exp": now + timedelta(hours=1)},
        signing_key,
        algorithm="RS256",
    )

    policy = authorizer_app.lambda_handler(auth_event(incomplete), None)

    assert effect_of(policy) == "Deny"


def test_unsigned_token_is_denied(authorizer_app):
    """An alg=none token must never be trusted."""
    now = datetime.now(tz=timezone.utc)
    unsigned = jwt.encode(
        {
            "sub": SUB,
            "iss": ISSUER,
            "iat": now,
            "exp": now + timedelta(hours=1),
            "token_use": "access",
            "client_id": APP_CLIENT_ID,
        },
        key="",
        algorithm="none",
    )

    policy = authorizer_app.lambda_handler(auth_event(unsigned), None)

    assert effect_of(policy) == "Deny"


# --------------------------------------------------------------------------
# Caching behaviour of the module-level JWKS client
# --------------------------------------------------------------------------


def test_jwks_client_is_reused_across_invocations(authorizer_app, signing_key):
    """The client lives at module level, so a warm container reuses it."""
    first = authorizer_app._jwk_client

    for _ in range(3):
        authorizer_app.lambda_handler(auth_event(make_token(signing_key)), None)

    assert authorizer_app._jwk_client is first
    assert first.calls == 3


def test_issuer_and_jwks_url_are_derived_from_the_environment(authorizer_app):
    """No hardcoded region: both come from env vars set by Terraform."""
    assert authorizer_app.ISSUER == ISSUER
    assert authorizer_app.JWKS_URL == f"{ISSUER}/.well-known/jwks.json"
    assert "us-west-2" in authorizer_app.JWKS_URL
