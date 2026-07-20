---
description: Fetch the node01 operator runbook before any homelab work. Use when working on node01, the Hetzner box, the shared Caddy reverse proxy, a Docker Compose app stack, or a self-hosted app deploy. Loads the guide so deploys follow the canonical pattern and avoid the known footguns.
allowed-tools: Bash, Read
---

# Homelab Connect — node01 Operator Guide

The Hetzner homelab box (`node01`, one shared Caddy + per-app Docker Compose stacks) is documented in a **private repo**, not here. Always load the runbook before touching the box, the proxy, DNS, or an app stack — it carries the access details, the per-app quirks, and the footguns.

## Step 1 — Fetch the runbook

```bash
gh api repos/mrtysn/homelab/contents/docs/node01-guide.md --jq '.content' | base64 -d
```

Read it in full before acting. If this 404s, `gh` is not authenticated as the repo owner — run `gh auth status` and have the user sign in (`! gh auth login`). The repo is private, so an unauthenticated fetch genuinely fails.

## Step 2 — Operate per the guide

Follow the runbook's canonical steps for whatever the task is (new app deploy, Caddy route, DNS record, snapshot). Key invariants it documents, restated so you don't skip them:

- Apps publish **no public ports** — they `expose:` and join the external `proxy` Docker network. Only the reverse proxy binds 80/443.
- Caddy config is per-app; reload rather than restart after editing a route.
- Cloudflare A-records must be **DNS-only (grey cloud)** or ACME fails.
- Generate secrets **on the box** (`openssl rand -hex 32`); never paste them into chat, and never commit them here. Keep off-box copies (host backups roll back the whole machine).
- SSH is key-only. Host details are in the runbook — do not copy them into this file.

## Notes

- The runbook is the single source of truth; if it conflicts with this file, trust the runbook.
- **Keep identifiers out of this file.** It lives in a public repo. No IPs, hostnames, domains, app inventory, or resource IDs — those belong in the private runbook. A previous version leaked a secret-gist ID here, which made the whole runbook world-readable: GitHub "secret" gists are unlisted, not access-controlled, so the ID *is* the credential.
- This is a read/loader skill — it does not itself change the box. Confirm consequential, outward-facing actions (DNS changes, first deploy, secret rotation) with the user before executing.
