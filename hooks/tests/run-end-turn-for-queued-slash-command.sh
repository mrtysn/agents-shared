#!/bin/bash
# DESC: Run the end-turn-for-queued-slash-command hook against its cases

set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
exec python3 -I "$HERE/test_end_turn_for_queued_slash_command.py"
