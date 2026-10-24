resource "aws_cognito_user_pool" "users" {
  name = "${local.name_prefix}-users-pool"

  password_policy {
    minimum_length    = 8
    require_lowercase = true
    require_numbers   = true
    require_uppercase = true
    require_symbols   = false
  }

  # Self-signup is out of scope for the MVP; workshop users are created by an
  # administrator with the AWS CLI.
  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-users-pool"
  })
}

resource "aws_cognito_user_pool_client" "users" {
  name         = "${local.name_prefix}-users-client"
  user_pool_id = aws_cognito_user_pool.users.id

  # No client secret: the workshop mints tokens straight from the CLI.
  generate_secret = false

  explicit_auth_flows = [
    "ALLOW_ADMIN_USER_PASSWORD_AUTH",
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]

  access_token_validity  = 60
  id_token_validity      = 60
  refresh_token_validity = 1

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }
}
