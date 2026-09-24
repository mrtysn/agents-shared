# Normalise a shell command for the system-one Bash check: keep the first
# KEEP lines of every heredoc body and replace the rest with a marker.
#
# A heredoc body is mostly noise to the decision model (Python source, JSON,
# prose) and drove the false asks on ordinary file edits; the opening line
# and the first body lines carry what matters (the interpreter, the path).
# Both hooks/system-one-bash.sh (awk -f) and scripts/system-one-measure.py
# (subprocess) run this same program, so the hook and the harness build an
# identical state. POSIX awk; BSD awk on macOS is the reference.
#
# Usage: awk -v KEEP=2 -f system-one-bash-state.awk < command

BEGIN { if (KEEP == "") KEEP = 2; term = ""; n = 0 }
{
    if (term != "") {
        line = $0
        if (strip) sub(/^\t+/, "", line)
        if (line == term) {
            if (n > KEEP) print "<heredoc: " (n - KEEP) " more lines>"
            print $0
            term = ""; n = 0
            next
        }
        n++
        if (n <= KEEP) print $0
        next
    }
    print $0
    # opening: <<WORD, <<-WORD, <<'WORD', <<"WORD"; the first on the line wins
    if (match($0, /<<-?[ \t]*['"]?[A-Za-z_][A-Za-z0-9_]*['"]?/)) {
        op = substr($0, RSTART, RLENGTH)
        strip = (substr(op, 3, 1) == "-")
        gsub(/^<<-?[ \t]*['"]?/, "", op)
        gsub(/['"]$/, "", op)
        term = op; n = 0
    }
}
END {
    # unterminated heredoc: still summarise what was cut
    if (term != "" && n > KEEP) print "<heredoc: " (n - KEEP) " more lines>"
}
