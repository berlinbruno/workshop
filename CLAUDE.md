# AnyCompany Users Service

## Project Overview

Serverless Users Service for AnyCompany. A RESTful API for managing user records with
JWT-based authentication. All infrastructure is defined with Terraform and deployed to AWS.

## Technology Stack

- **IaC**: Terraform (`.tf` files in the `infrastructure/` directory), not SAM or CDK
- **Language**: Python 3.13. Run it as `python3.13`, never plain `python3`, which is the
  operating system's own, older Python, in every shell and script, including Terraform
  `local-exec` commands: `python3.13 -m pip install --user` for packages (no virtual
  environment), `python3.13 -m pytest` for tests, `python3.13 -m pip install -t build/<function>`
  for Lambda dependencies
- **Compute**: AWS Lambda with the `python3.13` runtime on the `arm64` architecture (the
  workstation is Graviton, so dependencies packaged on it, such as `cryptography`, are arm64
  builds)
- **Database**: Amazon DynamoDB (on-demand billing)
- **API**: Amazon API Gateway REST API (v1)
- **Auth**: Amazon Cognito User Pool + Lambda Token Authorizer

## Project Layout

- `infrastructure/`: all Terraform files; run `terraform` commands from this directory
- `src/`: Lambda source code, one folder per function (for example `src/users/`). Only your own
  code lives here; third-party packages never do
- `build/`: Lambda packages that Terraform assembles (source plus dependencies), not committed
- `tests/unit/`: unit tests
- `specs/`: requirements, design, and task specs for each feature

## Best Practices

- Use descriptive resource names with a consistent prefix to avoid naming collisions
- Never hardcode an AWS region: the AWS provider block has no `region` argument and no region
  variable, because it reads the region from the `AWS_REGION` environment variable
- Before every `terraform apply`, run `terraform plan -out=tfplan`, summarize what it adds,
  changes, and destroys, then apply that saved plan
- Everything is removed with `terraform destroy` at the end of the workshop, so never add
  `lifecycle { prevent_destroy = true }` blocks or deletion protection
- Lambda functions log with Python logging (`logging.getLogger()`) at INFO level, with the
  function's log format set to JSON. Pass fields in `extra={...}`, and never log a whole
  event or a token
- Lambda functions and the API stage have AWS X-Ray active tracing
- All HTTP responses include CORS headers, including API Gateway's own error responses
- Timestamps stored as ISO 8601 strings in UTC
- User IDs are UUIDs (uuid4) generated server-side on create
- A failed DynamoDB call returns a generic 500 message; the details go to the log
- Terraform resources are organized by concern (one `.tf` file per logical component)
- API Gateway is defined using an OpenAPI 3.0 JSON body for clear endpoint documentation

## Testing

- Unit tests live in `tests/unit/` and run with `python3.13 -m pytest`
- Use `moto` 5 (`mock_aws`) for AWS service mocking in unit tests
- Every Lambda function should have test coverage for its happy path and error cases