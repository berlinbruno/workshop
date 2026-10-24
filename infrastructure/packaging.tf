locals {
  build_root = "${path.module}/../build"
}

# src/users has no third-party dependencies, so the source directory is zipped
# directly and no build step is needed. source_dir packs directory *contents* at
# the zip root, which is what handler = "app.lambda_handler" requires.
data "archive_file" "users" {
  type       = "zip"
  source_dir = "${path.module}/../src/users"

  output_path = "${local.build_root}/users.zip"

  # Without this, the zip preserves on-disk file modes; an unusual umask then
  # ships unreadable files and Lambda fails with Runtime.ImportModuleError.
  output_file_mode = "0644"

  # Patterns are relative to source_dir, not path.module.
  excludes = [
    "__pycache__",
    "**/__pycache__",
    "*.pyc",
    "**/*.pyc",
  ]
}

# src/authorizer needs PyJWT and cryptography, so it is built before it is
# zipped. The build is a data source rather than a local-exec provisioner so
# that archive_file can depend on its *output* -- a real data dependency between
# two plan-phase reads. depends_on would not be enough: Terraform only defers a
# data source read to apply time while its dependency has pending changes, so
# once the build resource settled in state the archive would go back to reading
# at plan time and fail on any checkout where build/ is absent.
data "external" "authorizer_build" {
  program = [
    "${abspath(path.module)}/build_package.sh",
    "${abspath(path.module)}/../src/authorizer",
    "${abspath(path.module)}/../build/authorizer",
  ]
}

data "archive_file" "authorizer" {
  type       = "zip"
  source_dir = data.external.authorizer_build.result.build_dir

  output_path      = "${local.build_root}/authorizer.zip"
  output_file_mode = "0644"

  excludes = [
    "__pycache__",
    "**/__pycache__",
    "*.pyc",
    "**/*.pyc",
  ]
}
