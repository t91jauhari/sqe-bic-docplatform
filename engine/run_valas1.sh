#!/usr/bin/env bash
set -euo pipefail
exec bash "$(dirname "$0")/run_sample.sh" --document-type valas_declaration_1 "$@"
