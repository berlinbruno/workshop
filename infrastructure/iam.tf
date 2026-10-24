data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "users_crud" {
  name               = "${local.name_prefix}-users-crud-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-users-crud-role"
  })
}

data "aws_iam_policy_document" "users_crud" {
  statement {
    sid    = "UsersTableCrud"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem",
      "dynamodb:Scan",
    ]
    resources = [aws_dynamodb_table.users.arn]
  }

  statement {
    sid    = "FunctionLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    # The provider strips the :* suffix from the log group ARN, but these actions
    # act on the log-stream resource type, so it has to go back on.
    # CreateLogGroup is deliberately absent: logging.tf owns the group.
    resources = ["${aws_cloudwatch_log_group.users_crud.arn}:*"]
  }

  statement {
    sid    = "XRayWrite"
    effect = "Allow"
    actions = [
      "xray:PutTraceSegments",
      "xray:PutTelemetryRecords",
    ]
    # Both actions are grantless, so "*" is the only valid resource value.
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "users_crud" {
  name   = "${local.name_prefix}-users-crud-policy"
  role   = aws_iam_role.users_crud.id
  policy = data.aws_iam_policy_document.users_crud.json
}

resource "aws_iam_role" "authorizer" {
  name               = "${local.name_prefix}-authorizer-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-authorizer-role"
  })
}

# Logging and tracing only. The authorizer has no DynamoDB access of any kind,
# and needs no Cognito permissions either: it fetches the JWKS over public
# HTTPS and verifies tokens locally.
data "aws_iam_policy_document" "authorizer" {
  statement {
    sid    = "FunctionLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["${aws_cloudwatch_log_group.authorizer.arn}:*"]
  }

  statement {
    sid    = "XRayWrite"
    effect = "Allow"
    actions = [
      "xray:PutTraceSegments",
      "xray:PutTelemetryRecords",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "authorizer" {
  name   = "${local.name_prefix}-authorizer-policy"
  role   = aws_iam_role.authorizer.id
  policy = data.aws_iam_policy_document.authorizer.json
}
