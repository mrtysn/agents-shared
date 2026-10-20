#!/bin/bash
# DESC: Run the require-user-quote-before-session-message PreToolUse hook against its cases

set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
exec python3 -I "$HERE/test_require_user_quote_before_session_message.py"
