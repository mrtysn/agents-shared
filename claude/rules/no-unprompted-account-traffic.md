# Never initiate traffic against the user's logged-in accounts

**The fetchers exist for the user to invoke, not for an agent to run because
links appeared.** Ingesting a list of links is not permission to generate
traffic against the platforms they point at.

It is the user's real account and their risk budget — rate limits, automated-
access flags, and bans land on them, not on the session that offered to be
helpful. A bulk pass over someone's saved posts is exactly the shape of traffic
platforms act on.

## What to do instead

- Bare links go onto a worklist. That costs nothing and loses nothing.
- Content arrives when the user captures pages themselves, or when they run the
  fetcher. Both already exist; neither is yours to trigger.
- Never propose a bulk fetch against the user's own session. If they want it,
  they will say so.

This is about traffic tied to *their* identity. Fetching a public page with no
session attached is ordinary work and this rule does not touch it.
