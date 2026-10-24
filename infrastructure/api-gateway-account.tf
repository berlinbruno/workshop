# REST API access logging requires an API Gateway CloudWatch Logs role set at the
# ACCOUNT level. This account had no cloudwatchRoleArn, so nothing is overwritten
# here, but note the setting is account-wide rather than per-API.

data "aws_iam_policy_document" "apigateway_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["apigateway.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "apigateway_cloudwatch" {
  name               = "${local.name_prefix}-apigateway-cloudwatch-role"
  assume_role_policy = data.aws_iam_policy_document.apigateway_assume_role.json

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-apigateway-cloudwatch-role"
  })
}

# API Gateway pushes logs for whatever APIs the account hosts, so this one is the
# AWS-managed policy rather than a per-log-group statement.
resource "aws_iam_role_policy_attachment" "apigateway_cloudwatch" {
  role       = aws_iam_role.apigateway_cloudwatch.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonAPIGatewayPushToCloudWatchLogs"
}

resource "aws_api_gateway_account" "main" {
  cloudwatch_role_arn = aws_iam_role.apigateway_cloudwatch.arn

  depends_on = [aws_iam_role_policy_attachment.apigateway_cloudwatch]
}
