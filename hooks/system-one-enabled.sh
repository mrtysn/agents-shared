# Sourced by hooks/system-one-*.sh (not run): the system-one on/off switch.
#
#   . "$(dirname "${BASH_SOURCE[0]}")/system-one-enabled.sh"
#   system_one_enabled || exit 0
#
# system_one_enabled succeeds unless SYSTEM_ONE_ENABLED is 0. An exported
# SYSTEM_ONE_ENABLED wins over ${CLAUDE_CONFIG_DIR:-~/.claude}/system-one.local.sh,
# the file is sourced in a subshell (so nothing it assigns leaks into the hook),
# and a missing or unreadable file, or a file that does not set the key, means
# enabled: a hook's other early exits own those cases. Set and cleared by
# `system-one disable` / `system-one enable`. Bash 3.2, like the hooks.

system_one_enabled() {
    local cfg="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/system-one.local.sh"
    local pre="${SYSTEM_ONE_ENABLED:-}" file=""
    if [ -z "$pre" ] && [ -r "$cfg" ]; then
        file=$( ( . "$cfg" >/dev/null 2>&1; printf '%s' "${SYSTEM_ONE_ENABLED:-}" ) ) || file=""
    fi
    [ "${pre:-${file:-1}}" != 0 ]
}
