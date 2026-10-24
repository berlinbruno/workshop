locals {
  api_name = "${local.name_prefix}-users-api"

  # A top-level OpenAPI "security" requirement applies to every operation, so the
  # two authorization phases never repeat per-method config. While
  # authorizer_enabled is false, every method is AWS_IAM; the authorizer in
  # Task 4 flips it. No method is ever deployed with authorization NONE.
  api_body = templatefile("${path.module}/openapi/users-api.json.tftpl", {
    api_name              = local.api_name
    lambda_invoke_arn     = aws_lambda_function.users_crud.invoke_arn
    authorizer_enabled    = var.authorizer_enabled
    authorizer_invoke_arn = aws_lambda_function.authorizer.invoke_arn
  })
}

resource "aws_api_gateway_rest_api" "users" {
  name        = local.api_name
  description = "Serverless Users Service REST API"
  body        = local.api_body

  endpoint_configuration {
    types = ["REGIONAL"]
  }

  tags = merge(local.common_tags, {
    Name = local.api_name
  })
}

# CORS headers on API Gateway's own error responses, which never reach the Lambda
# function. The inner single quotes are required: the values are mapped as
# static strings.
resource "aws_api_gateway_gateway_response" "default_4xx" {
  rest_api_id   = aws_api_gateway_rest_api.users.id
  response_type = "DEFAULT_4XX"

  # Declared explicitly to match what API Gateway applies by default. Leaving it
  # out makes Terraform delete it, which empties the JSON error body and shows
  # up as a perpetual diff.
  response_templates = {
    "application/json" = "{\"message\":$context.error.messageString}"
  }

  response_parameters = {
    "gatewayresponse.header.Access-Control-Allow-Origin"  = "'*'"
    "gatewayresponse.header.Access-Control-Allow-Headers" = "'Content-Type,Authorization'"
    "gatewayresponse.header.Access-Control-Allow-Methods" = "'GET,POST,PUT,DELETE,OPTIONS'"
  }

  # Importing the OpenAPI body uses PutRestApi in overwrite mode, which resets
  # gateway responses to the AWS defaults and silently drops these CORS headers.
  # Terraform does not notice on its own, because its state still records them,
  # so the responses are recreated whenever the API definition changes.
  lifecycle {
    replace_triggered_by = [aws_api_gateway_rest_api.users]
  }
}

resource "aws_api_gateway_gateway_response" "default_5xx" {
  rest_api_id   = aws_api_gateway_rest_api.users.id
  response_type = "DEFAULT_5XX"

  response_templates = {
    "application/json" = "{\"message\":$context.error.messageString}"
  }

  response_parameters = {
    "gatewayresponse.header.Access-Control-Allow-Origin"  = "'*'"
    "gatewayresponse.header.Access-Control-Allow-Headers" = "'Content-Type,Authorization'"
    "gatewayresponse.header.Access-Control-Allow-Methods" = "'GET,POST,PUT,DELETE,OPTIONS'"
  }

  lifecycle {
    replace_triggered_by = [aws_api_gateway_rest_api.users]
  }
}

resource "aws_api_gateway_deployment" "users" {
  rest_api_id = aws_api_gateway_rest_api.users.id

  # Redeploy whenever the API definition or the gateway responses change.
  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_rest_api.users.body,
      aws_api_gateway_gateway_response.default_4xx.response_parameters,
      aws_api_gateway_gateway_response.default_5xx.response_parameters,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_api_gateway_stage" "prod" {
  rest_api_id   = aws_api_gateway_rest_api.users.id
  deployment_id = aws_api_gateway_deployment.users.id
  stage_name    = var.api_stage_name

  xray_tracing_enabled = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_access.arn
    format = jsonencode({
      requestId      = "$context.requestId"
      ip             = "$context.identity.sourceIp"
      requestTime    = "$context.requestTime"
      httpMethod     = "$context.httpMethod"
      resourcePath   = "$context.resourcePath"
      status         = "$context.status"
      protocol       = "$context.protocol"
      responseLength = "$context.responseLength"
    })
  }

  # Access logging silently fails unless the account-level CloudWatch role exists.
  depends_on = [aws_api_gateway_account.main]

  tags = merge(local.common_tags, {
    Name = "${local.api_name}-${var.api_stage_name}"
  })
}

resource "aws_lambda_permission" "api_invoke_users_crud" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.users_crud.function_name
  principal     = "apigateway.amazonaws.com"

  # Scoped to this API; the wildcards cover every method and path in it.
  source_arn = "${aws_api_gateway_rest_api.users.execution_arn}/*/*"
}
