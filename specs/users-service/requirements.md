# Users Service — Requirements

## Introduction

The Users Service is a serverless REST API for managing user records. It exposes CRUD
operations over HTTPS, stores records in Amazon DynamoDB, and requires a valid Amazon
Cognito access token for every call. This document defines the MVP scope for a
60-minute build.

A user record consists of:

| Field       | Type   | Origin                                      |
| ----------- | ------ | ------------------------------------------- |
| `userid`    | String | Server-generated uuid4, immutable           |
| `name`      | String | Client-supplied, required, non-empty        |
| `email`     | String | Client-supplied, required, non-empty        |
| `createdAt` | String | Server-generated ISO 8601 UTC, immutable    |
| `updatedAt` | String | Server-generated ISO 8601 UTC, set on write |

## User Story 1 — Create a user record

As an API client, I want to submit a name and email so that a new user record is created
with an identifier I can use for later operations.

### Acceptance Criteria

1. WHEN a client sends `POST /users` with a JSON body containing a non-empty `name` and a
   non-empty `email`, the service SHALL generate a uuid4 `userid`, store the record, and
   respond `201` with the complete record including `createdAt` and `updatedAt`.
2. WHEN a client sends `POST /users` with `name` or `email` missing, empty, blank, or not a
   string, the service SHALL respond `400` with a JSON `message` naming the invalid field
   and SHALL NOT write any record.
3. WHEN a client sends `POST /users` with a body that is not valid JSON, the service SHALL
   respond `400` with a JSON `message` and SHALL NOT write any record.
4. WHEN a client sends `POST /users` including a `userid`, `createdAt`, or `updatedAt` field,
   the service SHALL ignore those client-supplied values and use server-generated ones.
5. WHEN a record is created, `createdAt` and `updatedAt` SHALL hold the same timestamp.

## User Story 2 — Retrieve user records

As an API client, I want to list all users and fetch one user by identifier so that I can
display user data.

### Acceptance Criteria

1. WHEN a client sends `GET /users`, the service SHALL respond `200` with a JSON object
   containing a `users` array of complete records and a `count` of the records returned.
2. WHEN a client sends `GET /users` and the table is empty, the service SHALL respond `200`
   with an empty `users` array and a `count` of `0`.
3. WHEN a client sends `GET /users/{userid}` for a stored record, the service SHALL respond
   `200` with that complete record.
4. WHEN a client sends `GET /users/{userid}` for a `userid` that is not stored, the service
   SHALL respond `404` with a JSON `message`.

## User Story 3 — Update and delete a user record

As an API client, I want to change or remove an existing user so that stored data stays
accurate.

### Acceptance Criteria

1. WHEN a client sends `PUT /users/{userid}` for a stored record with a non-empty `name` and
   a non-empty `email`, the service SHALL overwrite both fields, refresh `updatedAt`,
   preserve `userid` and `createdAt`, and respond `200` with the updated record.
2. WHEN a client sends `PUT /users/{userid}` with `name` or `email` missing, empty, blank, or
   not a string, the service SHALL respond `400` with a JSON `message` and SHALL NOT modify
   the record.
3. WHEN a client sends `PUT /users/{userid}` for a `userid` that is not stored, the service
   SHALL respond `404` with a JSON `message` and SHALL NOT create a record.
4. WHEN a client sends `DELETE /users/{userid}` for a stored record, the service SHALL remove
   the record and respond `200` with an empty JSON object.
5. WHEN a client sends `DELETE /users/{userid}` for a `userid` that is not stored, the service
   SHALL respond `404` with a JSON `message`.

## User Story 4 — Authenticated access only

As the service owner, I want every endpoint to require a valid Cognito access token issued
for my app client so that unauthenticated or wrongly scoped callers cannot reach user data.

### Acceptance Criteria

1. WHEN a client calls any endpoint without an `Authorization` header, the API SHALL reject
   the request with `401` and SHALL NOT invoke the CRUD function.
2. WHEN a client calls any endpoint with a token whose signature does not verify against the
   user pool's JWKS, or which is expired, or whose issuer is not this user pool, the API
   SHALL reject the request with `403` and SHALL NOT invoke the CRUD function.
3. WHEN a client presents a Cognito ID token rather than an access token (`token_use` is not
   `access`), the API SHALL reject the request with `403`.
4. WHEN a client presents an access token whose `client_id` is not this app client, the API
   SHALL reject the request with `403`.
5. WHEN a client presents a valid access token, the API SHALL invoke the CRUD function and
   SHALL make the token's `sub` and `client_id` available to it as authorizer context.
6. WHEN the authorizer grants access, the returned policy SHALL cover every method and path
   in the stage, so that one cached decision authorizes any subsequent endpoint.
7. WHILE the Lambda authorizer does not yet exist, every method SHALL use `AWS_IAM`
   authorization, so that the API never serves an unauthenticated request at any point in
   its deployment history.

## Non-functional Requirements

1. Both Lambda functions SHALL log in JSON at INFO level via Python `logging`, passing fields
   through `extra={...}`, and SHALL NOT log a whole event or any token.
2. Both Lambda functions and the `prod` stage SHALL have AWS X-Ray active tracing enabled,
   and the stage SHALL write JSON access logs to CloudWatch Logs.
3. Every service response, and API Gateway's own `DEFAULT_4XX` and `DEFAULT_5XX` gateway
   responses, SHALL include CORS headers.
4. WHEN a DynamoDB call fails, the service SHALL respond `500` with a generic `message` and
   SHALL log the underlying error.
5. WHEN a request reaches an unsupported method and path combination, the service SHALL
   respond `404` with a JSON `message`.
6. The CRUD function's IAM role SHALL permit only `GetItem`, `PutItem`, `UpdateItem`,
   `DeleteItem`, and `Scan` on the users table, and the authorizer's role SHALL have no
   DynamoDB permissions at all.

## Out of Scope for the MVP

Search or filter endpoints; secondary indexes; email uniqueness enforcement;
admin-only or role-based rules; pagination of `GET /users`; user self-signup flows;
CORS preflight (`OPTIONS`) methods.
