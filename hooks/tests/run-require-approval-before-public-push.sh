#!/bin/bash
# DESC: Run the require-approval-before-public-push PreToolUse hook against its cases

set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
exec python3 -I "$HERE/test_require_approval_before_public_push.py"
