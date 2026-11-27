#!/bin/bash
# Preserve the root build command; implementation lives with build scripts.
set -e
exec bash "$(dirname "$0")/scripts/build.sh" "$@"
