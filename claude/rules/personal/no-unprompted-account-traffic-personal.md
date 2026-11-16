# Account traffic on the personal machine

The personal-profile half of [no unprompted account traffic](../no-unprompted-account-traffic.md):
the gateway, proxy and logins that exist only on the owner's own machines.

Plain HTTP requests for pages, feeds and API responses go through
`fetch-anything-agent get URL`, which leaves from the home address under the gateway's
budget and cool-down; yt-dlp, SDKs and browsers stay direct. A refusal the gateway
reports is its cool-down for the site: wait it out, do not re-send. Where
agent-request-limiter answers 429, stop and tell the user.

The user's own sites behind Authelia (`*.mertyas.in`) take an agent login: a direct
`curl -H "$(agent-auth header)"` from the project folder, never through the gateway.
Never report such a site unreachable without having run it; when it refuses, say
that no login exists for this folder.

The full text appears the first time a session runs a network command.
