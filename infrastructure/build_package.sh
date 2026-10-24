#!/usr/bin/env bash
#
# Build a Lambda deployment directory: third-party dependencies plus handler
# source, staged under build/ and never under src/.
#
# Invoked by Terraform as a `data "external"` program, so that the build is a
# plan-phase read that `archive_file` can take a real data dependency on. That
# ordering is why a bare `terraform plan` works on a clean checkout: a
# `local-exec` build would only run during apply, after the archive data source
# has already tried to read a directory that does not exist yet.
#
# Usage: build_package.sh <src-dir> <build-dir>
# Contract: human-readable output on stderr, a single JSON object on stdout.

set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 <src-dir> <build-dir>" >&2
  exit 1
fi

SRC_DIR="$1"
BUILD_DIR="$2"

if [[ -z "$SRC_DIR" || -z "$BUILD_DIR" ]]; then
  echo "error: both src-dir and build-dir must be non-empty" >&2
  exit 1
fi

if [[ ! -d "$SRC_DIR" ]]; then
  echo "error: source directory does not exist: $SRC_DIR" >&2
  exit 1
fi

SRC_DIR="$(realpath "$SRC_DIR")"
BUILD_DIR="$(realpath -m "$BUILD_DIR")"

# stdout is reserved for the JSON result, so everything in here goes to stderr.
{
  echo "building $SRC_DIR -> $BUILD_DIR"
  rm -rf "$BUILD_DIR"
  mkdir -p "$BUILD_DIR"

  if [[ -f "$SRC_DIR/requirements.txt" ]]; then
    # The platform tag is pinned rather than derived from the local glibc: a
    # plain install on this host resolves manylinux_2_34_aarch64, which happens
    # to work here but would produce a package the Lambda runtime cannot load
    # if the workstation were ever newer. --only-binary makes pip fail loudly
    # instead of quietly building a host-specific sdist.
    python3.13 -m pip install \
      --target "$BUILD_DIR" \
      --platform manylinux2014_aarch64 \
      --implementation cp \
      --python-version 3.13 \
      --only-binary=:all: \
      --upgrade \
      --quiet \
      -r "$SRC_DIR/requirements.txt"
  fi

  # Handler source goes in last, at the zip root, so that the Lambda handler
  # string "app.lambda_handler" resolves.
  cp -R "$SRC_DIR"/. "$BUILD_DIR"/
  rm -f "$BUILD_DIR/requirements.txt"

  # Bytecode compiled here may not match the Lambda execution environment.
  find "$BUILD_DIR" -type d -name '__pycache__' -prune -exec rm -rf {} +
  find "$BUILD_DIR" -type f -name '*.pyc' -delete

  echo "build complete: $(find "$BUILD_DIR" -type f | wc -l) files"
} >&2

printf '{"build_dir":"%s"}' "$BUILD_DIR"
