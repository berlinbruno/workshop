terraform {
  required_version = ">= 1.0.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.0"
    }

    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.8"
    }

    external = {
      source  = "hashicorp/external"
      version = "~> 2.3"
    }
  }
}
