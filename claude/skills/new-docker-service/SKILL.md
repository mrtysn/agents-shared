---
description: Start a new service for the server on the project-lifecycle pipeline — a Docker Compose stack behind the shared Caddy and the login portal, with its route, env keys and deploy already defined — then create its GitHub repo. Use when the user asks for a new service, API, bot or web app to run on the server.
argument-hint: [service name] [host name]
allowed-tools: Bash, Read, Write, Edit, AskUserQuestion, Skill
---

# New Docker Service Skill

Scaffold a server stack with `project-lifecycle init docker-service`, prove its compose file
parses, then hand the directory to `/new-repo`. The templates live in project-lifecycle
(`project_lifecycle/init.py`); this skill only asks what a person must decide and runs the
command. Any agent can run the command without this skill.

## Required inputs (ask if missing)

Ask with AskUserQuestion, in one call, only for what the user will see or type:

1. **Service name** — what people call it (`Fetch Anything`). The directory, the tool slug
   (`fetch-anything`), the container name, `/opt/<slug>` on the server and the route file
   `<slug>.caddy` all derive from it; say so, and offer `--tool` only for a different slug.
2. **Host name** — where it is served (`fetch.mertyas.in`). It goes into the route and the
   checks; the DNS record for it is the user's, DNS-only.

Do not ask about the repo here; `/new-repo` asks its own questions. Do not ask which groups
may open it: the Authelia rule is a separate step in the homelab repo (below), with
`group:family` as the runbook's default.

## Steps

1. **Directory**: the current directory if it has none of `project-lifecycle.json`,
   `docker-compose.yml`, `Dockerfile`, `.env.example`, `CLAUDE.md`; otherwise `mkdir` the slug
   under the current directory and `cd` into it. `init` refuses to overwrite and names what
   is in the way: stop and report, never delete.
2. **Scaffold**:

       project-lifecycle init docker-service --name "<Service Name>" --site <host name> [--tool <slug>]

   Relay the files it wrote: the manifest, `docker-compose.yml` (one container, no public
   port, on the `proxy` network, memory limit, healthcheck), `Dockerfile` (a placeholder
   serving on 8080; the service replaces it), `<slug>.caddy` (gated by the portal),
   `.env.example`, `CLAUDE.md`.
3. **Prove it**: `project-lifecycle test` must pass (it parses the compose file). Report any
   failure as is.
4. **Repo**: invoke `/new-repo` with the Skill tool, passing the slug and a one-line
   description built from the service name and host.
5. **Report**, as the first deploy's order, which the user carries out when the service is
   written: the DNS record; the secret manager config with the keys of `.env.example`,
   pulled to `/opt/<slug>/.env` by the server's deploy script (add the app to that script's
   list and project map in the homelab repo); the `access_control` rule for the host in the
   Authelia configuration tracked in the homelab repo, deployed and Authelia restarted; then
   `project-lifecycle deploy` and `project-lifecycle status`. Also the inventory row the
   homelab runbook requires for every route.

## What the scaffold already does

- `project-lifecycle deploy`: rsync to `/opt/<slug>` (data/, .env and local files excluded),
  install the route when it differs with a Caddy validate and reload, build on the server,
  `compose up`, wait for the container, check `/healthz` answers 200 and `/` is sent to the
  portal. `status`: deployed revision, container health, route match.
- Every deploy reports its result to the receiver under the tool slug.

## Pitfalls

- **Never create the server's `.env` or paste secrets anywhere.** Secrets are generated on
  the box and kept in the secret manager; the server's deploy script materialises them.
- **The route and the Authelia rule are two halves**: a route without a rule shows nothing;
  a rule without a route does nothing. The scaffold writes the route; the rule is the
  homelab repo's.
- **A route must not be installed before its DNS record exists**; Caddy would request a
  certificate it cannot get. DNS is always step one.
