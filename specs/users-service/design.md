# Users Service — Design

## Overview

A single CRUD Lambda function sits behind an API Gateway REST API, fronted by a Lambda TOKEN
authorizer that validates Cognito access tokens. User records live in one DynamoDB table
keyed by `userid`. All infrastructure is Terraform in `infrastructure/`; all handler code is
Python 3.13 in `src/`, packaged into `build/` at apply time.

Resource names derive from `var.workshop_stack_base_name` (`workshop`), and the region comes
from `AWS_REGION` via the provider, read in code as `data.aws_region.current.region`.

## Architecture

    Client (curl)
        │  Authorization: Bearer <Cognito access token>
        ▼
    ┌─────────────────────────────────────────────────────┐
    │ API Gateway REST API  "workshop-users-api"          │
    │ OpenAPI 3.0 body · stage "prod" · X-Ray · access    │
    │ logs · DEFAULT_4XX / DEFAULT_5XX CORS headers       │
    └───────┬──────────────────────────────────┬──────────┘
            │ TOKEN authorizer                 │ AWS_PROXY
            ▼                                  ▼
    ┌───────────────────────┐        ┌────────────────────────┐
    │ workshop-authorizer   │        │ workshop-users-crud    │
    │ python3.13 · arm64    │        │ python3.13 · arm64     │
    │ PyJWT + cryptography  │        │ boto3 (runtime)        │
    │ JWKS cached at module │        │ routes on httpMethod   │
    └───────┬───────────────┘        │ + resource             │
            │ JWKS over HTTPS        └───────┬────────────────┘
            ▼                                │
    ┌───────────────────────┐                ▼
    │ Cognito User Pool     │        ┌────────────────────────┐
    │ + app client          │        │ DynamoDB workshop-users│
    └───────────────────────┘        │ PK userid (S)          │
                                     │ PAY_PER_REQUEST        │
                                     └────────────────────────┘

    Both functions → CloudWatch Logs (JSON) and X-Ray

## Components

| Component          | Resource                               | Notes                                                       |
| ------------------ | -------------------------------------- | ----------------------------------------------------------- |
| Users table        | `aws_dynamodb_table`                   | `workshop-users`, PK `userid` (S), on-demand, PITR on, no deletion protection |
| CRUD function      | `aws_lambda_function`                  | `workshop-users-crud`, python3.13, arm64, env `TABLE_NAME`  |
| Authorizer         | `aws_lambda_function`                  | `workshop-authorizer`, python3.13, arm64, env `USER_POOL_ID`, `APP_CLIENT_ID`; the region comes from the runtime |
| REST API           | `aws_api_gateway_rest_api`             | `body` from `templatefile()`, regional endpoint             |
| Stage              | `aws_api_gateway_deployment` + `aws_api_gateway_stage` | `prod`, `xray_tracing_enabled`, JSON `access_log_settings` |
| Gateway CORS       | `aws_api_gateway_gateway_response`     | `DEFAULT_4XX`, `DEFAULT_5XX`                                |
| Identity           | `aws_cognito_user_pool` + `aws_cognito_user_pool_client` | client with `USER_PASSWORD_AUTH` for workshop token minting |
| Roles              | `aws_iam_role` ×2 + inline policies    | least privilege, separate role per function                 |
| Log groups         | `aws_cloudwatch_log_group` ×3          | two function groups, one API access-log group               |

## Data Model

One item per user. Only `userid` is part of the schema; `name`, `email`, `createdAt`, and
`updatedAt` are schemaless attributes written on the item, so no `attribute` blocks beyond
the key appear in Terraform.

    {
      "userid":    "3f1c…",          # S, partition key, uuid4
      "name":      "Ada Lovelace",   # S
      "email":     "ada@example.com",# S
      "createdAt": "2026-10-24T09:15:00+00:00",
      "updatedAt": "2026-10-24T09:15:00+00:00"
    }

Access patterns and calls: list → `Scan`; read → `GetItem`; create → `PutItem` with
`ConditionExpression="attribute_not_exists(userid)"`; update → `UpdateItem` with
`ConditionExpression="attribute_exists(userid)"` so a missing record yields `404` rather
than an upsert; delete → `DeleteItem` with the same existence condition.

## API Contract

| Method | Resource          | Success        | Errors                |
| ------ | ----------------- | -------------- | --------------------- |
| GET    | `/users`          | `200` list     | `500`                 |
| POST   | `/users`          | `201` record   | `400`, `500`          |
| GET    | `/users/{userid}` | `200` record   | `404`, `500`          |
| PUT    | `/users/{userid}` | `200` record   | `400`, `404`, `500`   |
| DELETE | `/users/{userid}` | `200` `{}`     | `404`, `500`          |

## Request Flow

1. Client sends a request with `Authorization: Bearer <access token>`.
2. API Gateway extracts the header as the TOKEN authorizer's identity source. A missing
   header short-circuits to `401` without invoking the authorizer.
3. The authorizer strips an optional `Bearer ` prefix, fetches the user pool JWKS on first
   invocation and reuses the module-level cache afterwards, then verifies signature,
   expiry, and issuer with PyJWT.
4. It asserts `token_use == "access"` and `client_id == APP_CLIENT_ID`. Any failure raises,
   which API Gateway renders as `403`.
5. On success it returns an Allow policy whose resource is
   `arn:aws:execute-api:<region>:<account>:<api-id>/<stage>/*/*`, derived from the leading
   fields of `event["methodArn"]`, plus `principalId` set to the token `sub` and a context
   map of `sub` and `client_id`. The wildcard matters because the decision is cached per
   token for 300 seconds and must remain valid for every endpoint.
6. API Gateway invokes the CRUD function with `AWS_PROXY` integration.
7. The CRUD handler routes on `event["httpMethod"]` and `event["resource"]`, where
   `resource` is the literal template `/users` or `/users/{userid}`, never the expanded
   path. It validates input, calls DynamoDB, and returns a proxy response with CORS headers.
8. Both functions emit JSON logs; X-Ray records the trace across stage, authorizer, function,
   and DynamoDB.

## Authorization Bootstrap: Two Phases

Requirement 4.7 means the API must never exist in an unauthenticated state, which rules out
"deploy open, then add auth". A boolean variable `authorizer_enabled` (default `false`)
drives the OpenAPI template:

- **Phase 1 — `false`:** the template emits a `sigv4` security scheme
  (`x-amazon-apigateway-authtype: awsSigv4`) and a top-level `security` requirement, so every
  method is `AWS_IAM`. Verification uses `curl --aws-sigv4`.
- **Phase 2 — `true`:** the template emits the custom authorizer scheme with
  `x-amazon-apigateway-authorizer` of type `token`, and the same top-level `security` block
  now points at it.

A top-level `security` in OpenAPI 3.0 applies to every operation, so neither phase repeats
per-method auth config. Switching phases changes the `body`, which changes the deployment
trigger and redeploys the stage.

## Lambda Packaging

- `src/users/` has no third-party dependencies; `boto3` comes from the runtime. An
  `archive_file` data source zips the source directly.
- `src/authorizer/` needs `PyJWT` and `cryptography`. A `terraform_data` resource runs
  `python3.13 -m pip install -t build/authorizer PyJWT cryptography` and copies the handler
  in, triggered by a hash of the source and requirements; `archive_file` then zips
  `build/authorizer`. Because the workstation is arm64 Graviton, `cryptography` resolves to
  an arm64 wheel matching the function architecture.
- Third-party packages never live under `src/`; `build/` is generated and not committed.

## Observability

Each function configures `logging.getLogger()` at INFO and sets
`logging_config { log_format = "JSON" }` so CloudWatch parses fields passed via `extra={...}`.
Handlers log method, resource, and `userid`, never the event or the token. The stage's
`access_log_settings` uses a JSON format with `requestId`, `ip`, `httpMethod`,
`resourcePath`, `status`, `protocol`, and `responseLength`.

One account-level prerequisite: REST API access logging requires an API Gateway CloudWatch
Logs role set via `aws_api_gateway_account`. That setting is account-wide, so in a shared
account it may already be configured — check before creating a second role.

## Security

- Separate IAM role per function. The CRUD role gets exactly five DynamoDB actions scoped to
  the table ARN; the authorizer role gets logging and X-Ray only, and no DynamoDB access.
- `aws_lambda_permission` grants API Gateway invoke rights, scoped by `source_arn` to the API
  execution ARN for CRUD and to the authorizer ARN for the authorizer.
- Encryption at rest is on by default with an AWS-owned key; no customer-managed key for the
  MVP. TLS is inherent to both API Gateway and DynamoDB endpoints.
- No `prevent_destroy` and no deletion protection anywhere, so `terraform destroy` removes
  everything.

## Terraform File Layout

`provider.tf`, `versions.tf`, `variables.tf`, `outputs.tf` exist already. Added, one per
concern: `dynamodb.tf`, `iam.tf`, `lambda-users.tf`, `lambda-authorizer.tf`, `cognito.tf`,
`api-gateway.tf`, `logging.tf`, `packaging.tf`, plus the template
`openapi/users-api.json.tftpl`. Outputs expose the invoke URL, table name, user pool ID, and
app client ID.
