#!/bin/bash
# PreToolUse hook: Block editing files inside submodule directories
# Submodules are managed in their source repos — do not edit in place

set -e

INPUT=$(cat)

FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

if [ -z "$FILE_PATH" ]; then
    exit 0
fi

# Block writes into submodule directories
SUBMODULE_PATHS=(
    ".agents/"
)

for submodule in "${SUBMODULE_PATHS[@]}"; do
    if [[ "$FILE_PATH" == *"$submodule"* ]]; then
        echo "BLOCKED: '$FILE_PATH' is inside the '$submodule' submodule." >&2
        echo "Do not edit submodule contents in place." >&2
        echo "Edit the source repo instead, then update the submodule pointer." >&2
        exit 2
    fi
done

exit 0
