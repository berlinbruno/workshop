provider "aws" {
  # No region argument: the provider reads it from the AWS_REGION environment variable.
}

data "aws_region" "current" {}
