resource "aws_dynamodb_table" "users" {
  name         = "${local.name_prefix}-users"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "userid"

  # Only key attributes are declared. name, email, createdAt, and updatedAt are
  # schemaless and written on the item by the CRUD function.
  attribute {
    name = "userid"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  # The whole stack is torn down with terraform destroy at the end of the workshop.
  deletion_protection_enabled = false

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-users"
  })
}
