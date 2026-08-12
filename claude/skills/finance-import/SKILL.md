---
name: finance-import
description: Import freshly downloaded İş Bankası exports into Firefly III and refresh the burn/runway report. Use when the user says they downloaded bank files, wants the monthly finance refresh, or invokes /finance-import — typically right after the monthly Telegram reminder.
---

# Finance import — monthly refresh

The finance scripts live in `~/dev/finance` (local-only repo). Firefly III
runs on node01 at `https://firefly.mertyas.in` (Authelia-gated UI; `/api`
bypasses the gate and authenticates with the Firefly token in `.api.env`).
All commands run with the repo's venv: `cd ~/dev/finance && ./.venv/bin/python`.
If the remote API is unreachable, check node01 (`ssh node01 'docker ps'`) —
see the homelab runbook.

## Steps

1. **Sweep Downloads** — moves account `.xls` exports and card statement PDFs
   into `import/`, renaming card PDFs by currency + kesim date:

   ```sh
   ./.venv/bin/python scripts/sweep_downloads.py
   ```

   If it reports zero files, tell the user what to download (İş internet
   şubesi → hesap hareketleri per account as .xls; kart → Kredi Kartı Hesap
   Özetim → print-to-PDF per new dönem) and stop.

2. **Import** — idempotent; overlapping date ranges are safe:

   ```sh
   ./.venv/bin/python scripts/import_isbank.py
   ```

   **Every reconciliation line must end `OK`.** On a MISMATCH, do not
   continue — diagnose with `notes/parsing.md` (known quirks: ek hesap/KMH
   chain, page-seam duplicate rows, FX card payments, `1.234,-` amounts).

3. **Regenerate the report** (dated for today, into the notebook repo):

   ```sh
   ./.venv/bin/python scripts/burn_report.py --out ~/dev/notebook/$(date +%F)-burn-runway.html
   ```

   Then `open` the file.

4. **Tell the user what changed**: the new month's spend vs the running
   average, any category that jumped, updated runway. Check `TODO.md` for
   pending items worth surfacing (November repricings, unlabeled transfers).

## Notes

- Never `git add -f` anything; secrets live in gitignored `.env*` files.
- New accounts appearing in exports fail loudly — add them to `ACCOUNTS` in
  `scripts/import_isbank.py`.
- USD/EUR card statements are reference-only (not imported); only
  `maximiles-tl-*` PDFs are.
