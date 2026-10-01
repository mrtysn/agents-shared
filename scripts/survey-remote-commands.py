#!/usr/bin/env python3
# DESC: survey the ssh/scp/rsync commands agents ran against a host, classified, with ssh-request-guard replayed on each
"""
survey-remote-commands: inventory every Bash command that ssh/scp/rsyncs to a host.

Usage: survey-remote-commands.py --host PATTERN [--host PATTERN ...] [--since YYYY-MM-DD]
                                 [--out DIR] [--transcripts DIR]

Walks the Claude Code transcripts (<config dir>/projects/*/*.jsonl), keeps Bash
tool_use commands that ssh, scp, rsync, mosh or sftp to a host matching PATTERN,
classifies each (deploy, app CLI in a container, logs, DB read, secrets, ...),
replays hooks/ssh-request-guard.sh on it to see whether the hook would ask, and
flags scripts fed to the remote shell over stdin.

Prints a per-class table (commands, sessions, projects, hook asks) and the most
common docker exec targets. With --out DIR it also writes
remote-commands.tsv and remote-commands.json. Secret-looking strings are
redacted from everything printed or written.
"""
import argparse
import collections
import concurrent.futures
import glob
import json
import os
import re
import subprocess
import sys

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks", "ssh-request-guard.sh")
SSHWORD = re.compile(r"(^|[\s;&|(`/])(ssh|scp|rsync|autossh|mosh|sftp)\s")
LINE_HINT = re.compile(r"ssh|scp|rsync|mosh|sftp|tool_use_id")

# ---------------------------------------------------------------- redaction

SECRET_PATTERNS = [
    (re.compile(r"(?i)\b([\w.-]*(?:token|secret|passw(?:or)?d|passwd|api[_-]?key|apikey|auth|credential|private[_-]?key)[\w.-]*)(\s*[=:]\s*)(?:\"[^\"]*\"|'[^']*'|[^\s'\";&|]+)"), r"\1\2<redacted>"),
    (re.compile(r"(?i)(authorization:\s*(?:bearer|basic|token)\s+)[^\s'\"]+"), r"\1<redacted>"),
    (re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]{16,}"), r"\1 <redacted>"),
    (re.compile(r"(?i)(-H\s*['\"]?[\w-]*(?:key|token|auth)[\w-]*:\s*)[^'\"\s]+"), r"\1<redacted>"),
    (re.compile(r"(://[^/\s:@]+:)[^@\s/]+(@)"), r"\1<redacted>\2"),
    (re.compile(r"\b(?:sk|pk|rk|ghp|gho|ghs|github_pat|xox[abprs]|glpat|AKIA|AIza)[-_A-Za-z0-9]{16,}"), "<redacted>"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"), "<redacted>"),
    (re.compile(r"\b[0-9a-fA-F]{40,}\b"), "<redacted>"),
    (re.compile(r"\b(?=[A-Za-z0-9+/_-]*\d)(?=[A-Za-z0-9+/_-]*[A-Za-z])[A-Za-z0-9+/_-]{40,}={0,2}"), "<redacted>"),
]


def redact(text):
    if not text:
        return text
    for rx, repl in SECRET_PATTERNS:
        text = rx.sub(repl, text)
    return text


# ---------------------------------------------------------------- extraction

def transcripts_root(arg):
    if arg:
        return os.path.expanduser(arg)
    cfg = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    return os.path.join(cfg, "projects")


def extract(root, host_re, since):
    """Every Bash tool_use whose command ssh-es to the host, with its result head."""
    sshpat = re.compile(host_re)
    found = []
    for path in glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True):
        rel = os.path.relpath(path, root)
        project = rel.split(os.sep)[0]
        uses, results = {}, {}
        try:
            fh = open(path, errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                if not LINE_HINT.search(line):
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                content = (obj.get("message") or {}).get("content")
                if not isinstance(content, list):
                    continue
                for b in content:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "tool_use" and b.get("name") == "Bash":
                        cmd = (b.get("input") or {}).get("command", "")
                        if SSHWORD.search(cmd) and sshpat.search(cmd):
                            uses[b["id"]] = dict(
                                file=rel, project=project, session=obj.get("sessionId"),
                                ts=obj.get("timestamp"), command=cmd, subagent="subagents" in rel)
                    elif b.get("type") == "tool_result":
                        c = b.get("content")
                        if isinstance(c, list):
                            c = "\n".join(x.get("text", "") for x in c if isinstance(x, dict))
                        results[b.get("tool_use_id")] = dict(is_error=bool(b.get("is_error")), text=(c or "")[:600])
        for tid, u in uses.items():
            if since and (u["ts"] or "")[:10] < since:
                continue
            r = results.get(tid, {})
            u["is_error"] = r.get("is_error")
            u["result_head"] = r.get("text", "")
            found.append(u)
    found.sort(key=lambda u: u["ts"] or "")
    return found


# ---------------------------------------------------------------- classification

def quoted(s, i):
    """Text of the quoted string starting at s[i], and the index after it."""
    q = s[i]
    j = i + 1
    buf = []
    while j < len(s):
        c = s[j]
        if q == '"' and c == "\\":
            buf.append(s[j:j + 2])
            j += 2
            continue
        if c == q:
            if j + 1 < len(s) and s[j + 1] in "'\"":
                more, end = quoted(s, j + 1)
                return "".join(buf) + more, end
            return "".join(buf), j + 1
        buf.append(c)
        j += 1
    return "".join(buf), j


CLASSES = [
    ("python_inline_on_box", r"\bpython3?\s+(-c\b|-\s|-$|<<)"),
    ("db_query", r"sqlite3|\bpsql\b|\bmysql\b|manage\.py\s+(shell|dbshell)|\.sqlite|\.db\b|pg_dump|mariadb"),
    ("app_cli_in_container", r"docker\s+(compose\s+)?exec\b(?![^\n'\"]*\b(python3?\s+-c|sh\s+-c|cat|ls|printenv|wget|curl|env)\b)|docker\s+compose\s+run|manage\.py|\bocc\b|artisan"),
    ("compose_lifecycle", r"docker\s+compose\s+(up|down|build|restart|pull|stop|start|rm|create)|docker(-compose)?\s+(restart|stop|start|rm|build|pull|run)\b|docker\s+(image|system)\s+prune"),
    ("container_status", r"docker\s+(ps|inspect|stats|images|compose\s+ps|compose\s+config|network|volume|top|port)\b"),
    ("logs", r"docker\s+(compose\s+)?logs|journalctl|\.log\b|/var/log"),
    ("env_secret_read", r"\.env\b|printenv|\bsecret|token|password|credentials"),
    ("file_write_edit", r"sed\s+-i|\btee\b|cat\s*>|>\s*/(opt|etc|root|srv)|>>\s*/|\bmv\s|\bcp\s|chmod|chown|mkdir|\brm\s|ln\s+-s|install\s+-m|truncate"),
    ("systemd_timer", r"systemctl|\.timer\b|\.service\b|crontab"),
    ("reverse_proxy", r"caddy|nginx|traefik|Caddyfile"),
    ("disk_fs", r"\bdf\b|\bdu\b|findmnt|lsblk|\bmount\b|smartctl|zpool|btrfs|/mnt/"),
    ("git_on_box", r"\bgit\s"),
    ("loopback_http", r"(curl|wget)[^\n'\"]*(localhost|127\.0\.0\.1|http://[a-z][\w-]*:\d+)"),
    ("external_network", r"(curl|wget)[^\n]*https?://(?!localhost|127\.)[\w.-]+\.\w+|apt(-get)?\s+(update|install|upgrade)|pip\s+install|git\s+(clone|fetch|pull)|uvx?\s|npm\s+(i|install)"),
    ("process_net_diag", r"\bps\b|pgrep|pkill|\bkill\b|\bfree\b|uptime|\bss\s+-|netstat|tcpdump|/proc/|\btop\b|lsof|ufw|iptables|nft\b|tailscale|dig\b|resolvectl"),
    ("file_read", r"\bcat\b|\bls\b|\bgrep\b|\bfind\b|\bstat\b|\bhead\b|\btail\b|\bwc\b|\bsha256sum|\bdiff\b|\btest\s+-|\[\s+-[efd]"),
]
CLASSES = [(n, re.compile(rx, re.I if n == "env_secret_read" else 0)) for n, rx in CLASSES]

DEPLOY = re.compile(r"(^|[\s;&(/])[\w/.-]*deploy[\w.-]*\.(?:zsh|sh)\b(?!['\"])")
EXEC_OPT_ARG = {"-e", "--env", "-u", "--user", "-w", "--workdir", "--env-file", "--detach-keys"}
EXEC_RE = re.compile(r"docker(?:\s+compose)?\s+exec\s+([^;&|\n]*)")


def make_matchers(host_patterns):
    host = "(?:" + "|".join(f"(?:{p})" for p in host_patterns) + ")"
    hostre = r"(?:[\w.-]+@)?" + host
    ssh_at = re.compile(
        r"(?:^|[\s;&|(`/])ssh\b((?:\s+-[A-Za-z](?:\s+(?!" + host + r")[^\s'\"-][^\s]*)?)*)\s+" + hostre)
    xfer = re.compile(r"(?:^|[\s;&|(`])(scp|rsync)\b[^\n;|&]*" + hostre + ":")
    piped = re.compile(r"\|\s*ssh\b[^\n|]*" + hostre)
    return ssh_at, xfer, piped


def remote_parts(cmd, ssh_at, piped):
    """Remote command text of each ssh in cmd, and how its stdin is fed."""
    parts, stdin = [], []
    for m in ssh_at.finditer(cmd):
        i = m.end()
        while i < len(cmd) and cmd[i] in " \t":
            i += 1
        rest_line = cmd[i:].split("\n", 1)[0]
        if i < len(cmd) and cmd[i] in "'\"":
            body, end = quoted(cmd, i)
            tail = cmd[end:].split("\n", 1)[0]
        else:
            body = re.split(r"[|;&\n]", rest_line, 1)[0]
            tail = rest_line[len(body):]
        hd = re.search(r"<<-?\s*['\"]?(\w+)['\"]?", body + tail)
        if hd:
            delim = hd.group(1)
            after = cmd[m.end():].split("\n", 1)
            if len(after) > 1:
                rb = after[1].split("\n" + delim, 1)[0] if ("\n" + delim) in "\n" + after[1] else after[1]
                if after[1].startswith(delim):
                    rb = ""
                body = body + "\n" + rb
                stdin.append("heredoc")
        elif re.match(r"\s*<\s*\S", tail):
            stdin.append("file")
        if not body.strip() and not hd:
            stdin.append("interactive?")
        parts.append(body)
    if piped.search(cmd):
        stdin.append("pipe")
    return parts, stdin


def exec_target(remote):
    """Container name of the first docker exec in the remote text, or None."""
    m = EXEC_RE.search(remote)
    if not m:
        return None
    toks = m.group(1).split()
    i = 0
    while i < len(toks):
        t = toks[i]
        if t in EXEC_OPT_ARG:
            i += 2
        elif t.startswith("-"):
            i += 1
        else:
            return t.strip("'\"")
    return None


def classify(u, matchers):
    ssh_at, xfer, piped = matchers
    cmd = u["command"]
    parts, stdin = remote_parts(cmd, ssh_at, piped)
    remote = "\n".join(parts)
    labels = []
    has_xfer = bool(xfer.search(cmd))
    if DEPLOY.search(cmd):
        labels.append("deploy_script")
    if has_xfer:
        labels.append("transfer_scp_rsync")
    if any(s in ("heredoc", "file", "pipe") for s in stdin):
        labels.append("stdin_script")
    for name, rx in CLASSES:
        if rx.search(remote):
            labels.append(name)
    if not parts and not has_xfer and "deploy_script" not in labels:
        labels = ["mention_only"]
    elif not labels:
        labels = ["other"]
    return dict(u, remote=remote, stdin=stdin, labels=labels, remote_len=len(remote),
                docker_exec_target=exec_target(remote))


# ---------------------------------------------------------------- hook replay

def hook_asks(command):
    """True when ssh-request-guard.sh would ask about this command; None if it cannot run."""
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    try:
        r = subprocess.run(["bash", HOOK], input=payload, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return '"ask"' in r.stdout


# ---------------------------------------------------------------- output

def short_project(p):
    return p.lstrip("-")[-24:]


def main():
    ap = argparse.ArgumentParser(
        description="Inventory and classify the ssh/scp/rsync commands agents ran against a host.",
        usage="%(prog)s --host PATTERN [--host PATTERN ...] [--since YYYY-MM-DD] [--out DIR] [--transcripts DIR]")
    ap.add_argument("--host", action="append", required=True, metavar="PATTERN",
                    help="regex matching the host as it appears in commands (an ssh alias, an address); repeatable")
    ap.add_argument("--since", metavar="YYYY-MM-DD", help="only commands on or after this date")
    ap.add_argument("--out", metavar="DIR", help="write remote-commands.tsv and remote-commands.json here")
    ap.add_argument("--transcripts", metavar="DIR",
                    help="transcript root (default: $CLAUDE_CONFIG_DIR/projects, else ~/.claude/projects)")
    args = ap.parse_args()

    if args.since and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.since):
        ap.error("--since must be YYYY-MM-DD")
    try:
        for p in args.host:
            re.compile(p)
    except re.error as e:
        ap.error(f"bad --host pattern: {e}")
    root = transcripts_root(args.transcripts)
    if not os.path.isdir(root):
        sys.exit(f"transcript root not found: {root}")
    if not os.path.isfile(HOOK):
        sys.exit(f"hook not found: {os.path.normpath(HOOK)}")

    host_re = "(?:" + "|".join(f"(?:{p})" for p in args.host) + ")"
    matchers = make_matchers(args.host)
    raw = extract(root, host_re, args.since)
    rows = [classify(u, matchers) for u in raw]
    real = [u for u in rows if u["labels"] != ["mention_only"]]

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        asks = list(ex.map(lambda u: hook_asks(u["command"]), real))
    for u, a in zip(real, asks):
        u["hook_asks"] = a
    for u in rows:
        u.setdefault("hook_asks", None)

    for u in rows:
        u["command"] = redact(u["command"])
        u["remote"] = redact(u["remote"])
        u["result_head"] = redact(u["result_head"])

    print(f"{len(rows)} commands matched; {len(real)} real, {len(rows) - len(real)} mention only; "
          f"{len({u['session'] for u in real})} sessions; {len({u['project'] for u in real})} projects; "
          f"{sum(1 for u in real if u['hook_asks'])} hook asks")
    by = collections.defaultdict(lambda: [0, set(), set(), 0])
    for u in real:
        for label in u["labels"]:
            row = by[label]
            row[0] += 1
            row[1].add(u["session"])
            row[2].add(u["project"])
            row[3] += 1 if u["hook_asks"] else 0
    print(f"\n{'class':24} {'commands':>8} {'sessions':>8} {'projects':>8} {'hook-asks':>9}")
    for label, (n, s, p, a) in sorted(by.items(), key=lambda x: -x[1][0]):
        print(f"{label:24} {n:8} {len(s):8} {len(p):8} {a:9}")
    targets = collections.Counter(u["docker_exec_target"] for u in real if u["docker_exec_target"])
    if targets:
        print("\ntop docker exec targets")
        for t, n in targets.most_common(10):
            print(f"{n:6}  {t}")

    if args.out:
        out = os.path.expanduser(args.out)
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, "remote-commands.json"), "w") as fh:
            json.dump(rows, fh, indent=1)
        with open(os.path.join(out, "remote-commands.tsv"), "w") as fh:
            fh.write("ts\tproject\tsession\tsubagent\tlabels\tstdin\thook_asks\tdocker_exec_target\tis_error\tremote\n")
            for u in rows:
                fh.write("\t".join([
                    (u["ts"] or "")[:19], u["project"], u["session"] or "", str(u["subagent"]),
                    ",".join(u["labels"]), ",".join(u["stdin"]), str(u["hook_asks"]),
                    u["docker_exec_target"] or "", str(u["is_error"]),
                    " ".join(u["remote"].split())[:400]]) + "\n")
        print(f"\nwrote remote-commands.tsv and remote-commands.json to {out}")


if __name__ == "__main__":
    main()
