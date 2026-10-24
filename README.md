# workshop — Users Service

A serverless Users Service built with Terraform and Python, running on AWS Lambda
(python3.13, arm64).

## Layout

| Path                | Contents                                      |
| ------------------- | --------------------------------------------- |
| `src/users/`        | Users Lambda function source                  |
| `src/authorizer/`   | Authorizer Lambda function source             |
| `tests/unit/`       | Unit tests (pytest + moto)                    |
| `infrastructure/`   | Terraform configuration for all AWS resources |

## Getting started

The AWS region comes from the environment, so set it before running Terraform:

```bash
export AWS_REGION=<your-region>

cd infrastructure
terraform init
terraform plan -out=tfplan
terraform apply tfplan
```

Run the tests from the project root:

```bash
python3.13 -m pytest
```

Use `python3.13` rather than `python3` — see `CLAUDE.md` for the project conventions.

## Teardown

```bash
cd infrastructure
terraform destroy
```
