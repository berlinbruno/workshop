# Outputs for the Users Service stack.

output "invoke_url" {
  description = "Base URL of the deployed API stage."
  value       = aws_api_gateway_stage.prod.invoke_url
}

output "rest_api_id" {
  description = "Identifier of the REST API."
  value       = aws_api_gateway_rest_api.users.id
}

output "users_table_name" {
  description = "Name of the DynamoDB table holding user records."
  value       = aws_dynamodb_table.users.name
}

output "users_crud_function_name" {
  description = "Name of the CRUD Lambda function."
  value       = aws_lambda_function.users_crud.function_name
}

output "user_pool_id" {
  description = "Identifier of the Cognito user pool."
  value       = aws_cognito_user_pool.users.id
}

output "app_client_id" {
  description = "Identifier of the Cognito app client that tokens must be issued for."
  value       = aws_cognito_user_pool_client.users.id
}
