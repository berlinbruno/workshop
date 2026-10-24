# Log groups are created ahead of the functions and the API stage that write to
# them, so that retention is managed by Terraform rather than left to the implicit
# never-expire group Lambda would otherwise create.

resource "aws_cloudwatch_log_group" "users_crud" {
  name              = "/aws/lambda/${local.name_prefix}-users-crud"
  retention_in_days = var.log_retention_in_days

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-users-crud-logs"
  })
}

resource "aws_cloudwatch_log_group" "authorizer" {
  name              = "/aws/lambda/${local.name_prefix}-authorizer"
  retention_in_days = var.log_retention_in_days

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-authorizer-logs"
  })
}

resource "aws_cloudwatch_log_group" "api_access" {
  name              = "/aws/apigateway/${local.name_prefix}-users-api/access"
  retention_in_days = var.log_retention_in_days

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-users-api-access-logs"
  })
}
