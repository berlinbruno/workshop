variable "workshop_stack_base_name" {
  description = "Base name used for all resources in this stack."
  type        = string
  default     = "workshop"
}

variable "environment" {
  description = "Value of the Environment tag applied to all resources."
  type        = string
  default     = "Workshop"
}

variable "project" {
  description = "Value of the Project tag applied to all resources."
  type        = string
  default     = "Serverless with AI"
}

variable "api_stage_name" {
  description = "Name of the single API Gateway stage."
  type        = string
  default     = "prod"
}

variable "authorizer_enabled" {
  description = <<-EOT
    Whether every API method uses the Cognito Lambda TOKEN authorizer. While
    false, every method uses AWS_IAM authorization instead, so the API is never
    deployed with authorization NONE. Flipped to true in Task 4, once the
    authorizer function exists.
  EOT
  type        = bool
  default     = true
}

variable "log_retention_in_days" {
  description = "Retention for every CloudWatch log group in this stack."
  type        = number
  default     = 7
}
