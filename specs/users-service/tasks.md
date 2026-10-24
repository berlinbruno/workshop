# Users Service — Tasks

Six task groups, in order. Run `terraform` commands from `infrastructure/`, and `pytest` from
the project root. Every group that adds infrastructure ends with a saved-plan apply and a
check against the deployed resources. Unit tests arrive in Task 6.

## Task 1: Infrastructure Foundation

- [x] Add `dynamodb.tf` with `aws_dynamodb_table` `workshop-users`: `hash_key = "userid"`, one
      `attribute` block for `userid` (S), `billing_mode = "PAY_PER_REQUEST"`,
      `point_in_time_recovery` enabled, no deletion protection.
- [x] Add `logging.tf` with CloudWatch log groups for both functions
      (`/aws/lambda/workshop-users-crud`, `/aws/lambda/workshop-authorizer`) and for the API
      access logs, each with a short `retention_in_days`.
- [x] Add a `locals` block holding the common tags `Name`, `Environment` ("Workshop"), and
      `Project` ("Serverless with AI"), and apply them to every resource.
- [x] Run `terraform plan -out=tfplan`, summarize the adds, changes, and destroys, then
      `terraform apply tfplan`.
- [x] Verify with `aws dynamodb describe-table --table-name workshop-users` that the key
      schema is `userid` HASH, the billing mode is `PAY_PER_REQUEST`, and the status is
      `ACTIVE`.

## Task 2: Business Logic (CRUD Lambda)

- [x] Write `src/users/app.py`: a `lambda_handler` routing on `event["httpMethod"]` and
      `event["resource"]`, with one function per operation, uuid4 `userid` generation,
      ISO 8601 UTC timestamps, and shared response helpers that attach CORS headers.
- [x] Implement validation and error mapping: `400` for malformed JSON or a missing, blank, or
      non-string `name` or `email`; `404` for an unknown `userid` and for an unsupported
      method or resource; a generic `500` on DynamoDB failure with details sent to the log.
- [x] Configure JSON logging at INFO with fields passed via `extra={...}`, logging method,
      resource, and `userid` only.
- [x] Add `iam.tf` with the CRUD role, trust policy, basic execution logging, X-Ray write
      permissions, and a DynamoDB policy limited to `GetItem`, `PutItem`, `UpdateItem`,
      `DeleteItem`, and `Scan` on the table ARN.
- [x] Add `lambda-users.tf` and `packaging.tf`: `archive_file` over `src/users`, the function
      with python3.13 on arm64, `TABLE_NAME` env var, `tracing_config` Active, and
      `logging_config` with `log_format = "JSON"`.
- [x] Run `terraform plan -out=tfplan`, summarize, apply, then verify with
      `aws lambda invoke --function-name workshop-users-crud --payload` of a synthetic
      `POST /users` proxy event that the response is `201`, and confirm the item with
      `aws dynamodb scan --table-name workshop-users`.

## Task 3: API Gateway

- [x] Write `openapi/users-api.json.tftpl`: an OpenAPI 3.0 document with the five operations,
      `x-amazon-apigateway-integration` of type `aws_proxy` pointing at the CRUD function, and
      a top-level `security` requirement rendered from the `authorizer_enabled` variable,
      which stays `false` for now so every method is `AWS_IAM`.
- [x] Add `api-gateway.tf`: `aws_api_gateway_rest_api` with `body = templatefile(...)`,
      `aws_api_gateway_deployment` triggered by a hash of the body with
      `create_before_destroy`, and `aws_api_gateway_stage` `prod` with
      `xray_tracing_enabled` and JSON `access_log_settings`.
- [x] Add the `DEFAULT_4XX` and `DEFAULT_5XX` `aws_api_gateway_gateway_response` resources
      with CORS response parameters, the `aws_lambda_permission` for API Gateway to invoke the
      CRUD function scoped by `source_arn`, and an `aws_api_gateway_account` CloudWatch role
      if the account does not already have one.
- [x] Add an `invoke_url` output, run `terraform plan -out=tfplan`, summarize, and apply.
- [x] Verify the API is closed and functional: an unsigned `curl` to `/users` returns `403`
      with a missing-authentication message, and `curl --aws-sigv4 "aws:amz:$AWS_REGION:execute-api"`
      with your credentials returns `200`. Confirm CORS headers are present on the `403`.

## Task 4: Authentication

- [x] Add `cognito.tf`: `aws_cognito_user_pool` `workshop-users-pool` and an
      `aws_cognito_user_pool_client` with `USER_PASSWORD_AUTH` enabled and no client secret,
      plus outputs for the pool ID and client ID.
- [x] Write `src/authorizer/app.py`: strip the `Bearer` prefix, verify the token against a
      module-level cached JWKS with PyJWT, assert `token_use == "access"` and a matching
      `client_id`, and return an Allow policy whose resource wildcards every method and path
      in the stage, with `principalId` from `sub` and a context of `sub` and `client_id`.
      Raise `Exception("Unauthorized")` on any failure and never log the token.
- [x] Add `lambda-authorizer.tf` and extend `packaging.tf` with a `terraform_data` resource
      running `python3.13 -m pip install -t build/authorizer PyJWT cryptography`, then an
      `archive_file` over `build/authorizer`; add the authorizer role with logging and X-Ray
      only, and the `aws_lambda_permission` for API Gateway to invoke it.
- [x] Flip `authorizer_enabled` to `true` so the OpenAPI template emits the TOKEN authorizer
      security scheme with a 300-second result cache, run `terraform plan -out=tfplan`,
      summarize the method authorization change, and apply.
- [x] Create a workshop user with `aws cognito-idp admin-create-user` and
      `admin-set-user-password --permanent`, then mint tokens with
      `aws cognito-idp admin-initiate-auth --auth-flow ADMIN_USER_PASSWORD_AUTH`.
- [x] Verify with `curl`: no header returns `401`; a garbage token returns `403`; the ID token
      returns `403`; the access token returns `200`.

## Task 5: End-to-End Verification

- [x] Export the invoke URL and access token, then `curl -X POST /users` with a valid name and
      email and confirm `201` plus a uuid4 `userid`, `createdAt`, and `updatedAt`.
- [x] Walk the read path: `GET /users` returns the record in a `users` array with a `count`,
      and `GET /users/{userid}` returns the single record.
- [x] Walk the write path: `PUT /users/{userid}` returns `200` with a changed `name`, a
      refreshed `updatedAt`, and an unchanged `createdAt`; `DELETE /users/{userid}` returns
      `200` with `{}`; a follow-up `GET` returns `404`.
- [x] Exercise the error paths: `POST` with an empty `name` returns `400`, `POST` with
      malformed JSON returns `400`, and `GET /users/does-not-exist` returns `404`.
- [ ] Confirm observability: `aws logs tail /aws/lambda/workshop-users-crud` shows structured
      JSON entries with no event or token contents, the API access-log group has JSON entries,
      and `aws xray get-trace-summaries` shows traces spanning stage, authorizer, function,
      and DynamoDB.

## Task 6: Unit Tests

- [x] Install test dependencies with `python3.13 -m pip install --user pytest "moto[all]>=5"`
      and add `tests/unit/conftest.py` with fixtures that set fake AWS credentials and
      `TABLE_NAME`, and create the users table inside `mock_aws`.
- [x] Write `tests/unit/test_users.py` covering create, list, get, update, and delete happy
      paths against the mocked table, asserting status codes, body shape, and CORS headers.
- [x] Extend `tests/unit/test_users.py` with error cases: `400` for invalid or malformed
      input, `404` for an unknown `userid` on get, update, and delete, `404` for an
      unsupported route, and `500` when the DynamoDB call raises.
- [x] Write `tests/unit/test_authorizer.py` with a locally generated RSA key and a stubbed
      JWKS, covering an allowed access token, a rejected ID token, a wrong `client_id`, an
      expired token, a bad signature, and the wildcard shape of the returned policy resource.
- [x] Run `python3.13 -m pytest tests/unit -v` and confirm every test passes.
