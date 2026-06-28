---
description: Fetch the node01 operator runbook (a secret gist) before any homelab work. Use when working on node01, the Hetzner box, the shared Caddy reverse proxy, a Docker Compose app stack, or any *.mertyas.in deploy (moji, atlas, vikunja, ecleniyorum, etc.). Loads the guide so deploys follow the canonical pattern and avoid the known footguns.
allowed-tools: Bash, Read
---

# Homelab Connect — node01 Operator Guide

The Hetzner homelab box (`node01`, one shared Caddy + per-app Docker Compose stacks) is documented in a **secret GitHub gist**, not in any repo. Always load it before touching the box, the proxy, DNS, or an app stack — it carries the access details and the footguns (intentional `/opt/ecleniyorum` drift, grey-cloud DNS requirement, single-Caddy/443 rule, Vikunja webhook quirks, off-box secret backups).

## Step 1 — Fetch the runbook

```bash
gh gist view f2420c3f78f7110369ddd2d35687eebf
```

Read it in full before acting. If `gh` is not authenticated, run `gh auth status` and have the user sign in (`! gh auth login`) — the gist is private, so an unauthenticated fetch will fail.

## Step 2 — Operate per the guide

Follow the runbook's canonical steps for whatever the task is (new app deploy, Caddy route, DNS record, snapshot). Key invariants it documents, restated so you don't skip them:

- Apps publish **no public ports** — they `expose:` and join the external `proxy` Docker network. Only Caddy binds 80/443.
- Caddy routes live in `/opt/caddy/sites/<app>.caddy`; reload with
  `docker exec caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile`.
- Cloudflare A-records must be **DNS-only (grey cloud)** or ACME fails.
- Generate secrets **on the box** (`openssl rand -hex 32`); never paste them into chat. Keep off-box copies (Hetzner backups roll back the whole box).
- `ssh node01` → `root@167.233.28.221`, key-only.

## Notes

- The gist is the single source of truth; if it conflicts with this file, trust the gist (it's updated in place).
- This is a read/loader skill — it does not itself change the box. Confirm consequential, outward-facing actions (DNS changes, first deploy, secret rotation) with the user before executing.
