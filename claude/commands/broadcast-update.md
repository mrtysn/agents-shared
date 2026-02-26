---
description: Update agents-shared submodule in all consumer repos listed in consumers.local.
allowed-tools: Bash
---

Broadcast the latest agents-shared changes to all consumer repositories. This updates submodule pointers and re-runs init.sh for symlinks. It does NOT commit — that is each repo owner's responsibility.

**Steps:**

1. Verify `consumers.local` exists in the agents-shared repo root. The agents-shared repo is reachable from the current project at `.agents/`, or if you are already inside agents-shared, at the repo root. If `consumers.local` is missing, error with instructions to create it (one repo path per line).

2. Run the update script:
   ```bash
   bash .agents/scripts/update-consumers.sh
   ```

   If running from within agents-shared itself:
   ```bash
   bash scripts/update-consumers.sh
   ```

3. Report the results as printed by the script.

$ARGUMENTS
