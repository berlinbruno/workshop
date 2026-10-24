resource "aws_lambda_function" "authorizer" {
  function_name = "${local.name_prefix}-authorizer"
  role          = aws_iam_role.authorizer.arn

  filename    = data.archive_file.authorizer.output_path
  code_sha256 = data.archive_file.authorizer.output_base64sha256

  handler       = "app.lambda_handler"
  runtime       = "python3.13"
  architectures = ["arm64"]
  timeout       = 10
  # Slightly larger than the CRUD function: the first invocation imports
  # cryptography and fetches the JWKS.
  memory_size = 512

  environment {
    variables = {
      USER_POOL_ID  = aws_cognito_user_pool.users.id
      APP_CLIENT_ID = aws_cognito_user_pool_client.users.id
      # AWS_REGION is supplied by the runtime and cannot be set here.
    }
  }

  tracing_config {
    mode = "Active"
  }

  logging_config {
    log_format            = "JSON"
    application_log_level = "INFO"
    system_log_level      = "INFO"
    log_group             = aws_cloudwatch_log_group.authorizer.name
  }

  depends_on = [aws_iam_role_policy.authorizer]

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-authorizer"
  })
}

# The authorizer is declared in the OpenAPI body, so API Gateway generates its
# identifier on import and it cannot be referenced here. The wildcard scopes
# invoke rights to any authorizer belonging to this one API.
resource "aws_lambda_permission" "api_invoke_authorizer" {
  statement_id  = "AllowAPIGatewayInvokeAuthorizer"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.authorizer.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.users.execution_arn}/authorizers/*"
}
