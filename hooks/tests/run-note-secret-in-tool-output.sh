#!/bin/bash
# DESC: Run the note-secret-in-tool-output hook against its cases

set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
exec python3 -I "$HERE/test_note_secret_in_tool_output.py"
