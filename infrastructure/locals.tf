locals {
  # Prefix for every resource name in this stack.
  name_prefix = var.workshop_stack_base_name

  # Tags applied to every resource. Per-resource Name tags are merged in at the
  # resource, since Name has to be unique per resource.
  common_tags = {
    Environment = var.environment
    Project     = var.project
  }
}
