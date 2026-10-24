resource "aws_lambda_function" "users_crud" {
  function_name = "${local.name_prefix}-users-crud"
  role          = aws_iam_role.users_crud.arn

  filename = data.archive_file.users.output_path
  # code_sha256 reconciles against the CodeSha256 the Lambda API reports, so a
  # code change redeploys and an out-of-band console edit shows as drift.
  code_sha256 = data.archive_file.users.output_base64sha256

  handler       = "app.lambda_handler"
  runtime       = "python3.13"
  architectures = ["arm64"]
  timeout       = 10
  memory_size   = 256

  environment {
    variables = {
      TABLE_NAME = aws_dynamodb_table.users.name
    }
  }

  tracing_config {
    mode = "Active"
  }

  logging_config {
    log_format            = "JSON"
    application_log_level = "INFO"
    system_log_level      = "INFO"
    # Bind to the Terraform-managed group from logging.tf rather than letting
    # Lambda implicitly create a never-expiring one.
    log_group = aws_cloudwatch_log_group.users_crud.name
  }

  # The role has to carry its policy before the first invocation.
  depends_on = [aws_iam_role_policy.users_crud]

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-users-crud"
  })
}
