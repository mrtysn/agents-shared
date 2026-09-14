---
name: finance-import
description: Import freshly downloaded İş Bankası and Yapı Kredi exports into Firefly III and refresh the burn/runway report. Use when the user says they downloaded bank files, wants the monthly finance refresh, or invokes /finance-import — typically right after the monthly Telegram reminder.
---

# Finance import — monthly refresh

The finance scripts live in `$DEV_ROOT/finance` (its git remote is on node01). Firefly III
runs on node01 behind the shared Caddy (Authelia-gated UI; `/api`
bypasses the gate and authenticates with the Firefly token in `.api.env`).
All commands run with the repo's venv: `cd "$DEV_ROOT/finance" && ./.venv/bin/python`.
The host name is in `.api.env` (`FIREFLY_URL`) and the private homelab runbook
(`/homelab-connect`). If the remote API is unreachable, check node01
(`ssh node01 'docker ps'`) — see that runbook.

## Steps

1. **Sweep Downloads** — moves account `.xls` exports and statement PDFs into
   `import/`. PDFs are recognized by content, whatever they were saved as:
   Maximiles statements are named by currency + kesim, Yapı Kredi account
   movements by currency + date range, Worldcard statements by kesim (the
   last two into `import/yapikredi/`):

   ```sh
   ./.venv/bin/python scripts/sweep_downloads.py
   ```

   If it reports zero files, tell the user what to download and stop:
   - İş internet şubesi → hesap hareketleri per account as .xls, **starting on
     or before the last export's end date** (overlap by a day; a gap between
     exports is fatal), ending today
   - Kredi Kartı Hesap Özetim → print-to-PDF per new dönem, TL, USD and EUR
   - Kredi Kartı Son İşlemlerim → print-to-PDF per card (or copy-paste into a
     `.txt`), taken **after** the newest statement (an older capture is ignored);
     a card with no new transactions needs no page
   - Ecem's Yapı Kredi account PDFs and Worldcard statements, same overlap rule

2. **Import** — idempotent. Row ids are the bank's reference (İş) or the row's
   content (Yapı Kredi), so re-imports skip what Firefly holds; exports of one
   account are merged; opening balances never move later than the history
   Firefly already has, so a month-only export is safe:

   ```sh
   ./.venv/bin/python scripts/import_isbank.py
   ./.venv/bin/python scripts/import_yapikredi.py   # when Yapı Kredi files arrived
   ```

   **Every reconciliation line must end `OK`.** On a MISMATCH, do not
   continue — diagnose with `notes/parsing.md` (known quirks: ek hesap/KMH
   chain, page-seam duplicate rows, FX card payments, `1.234,-` amounts).

3. **Regenerate the report** (dated for today, into the notebook repo):

   ```sh
   ./.venv/bin/python scripts/burn_report.py --out "$DEV_ROOT/notebook/$(date +%F)-burn-runway.html"
   ```

   Then `open` the file.

4. **Tell the user what changed**: the new month's spend vs the running
   average, any category that jumped, updated runway. Check `TODO.md` for
   pending items worth surfacing (November repricings, unlabeled transfers).

## Notes

- **Browser alternative**: either spouse can upload files / paste captures at
  the Firefly host's `/upload` page (Authelia-gated) — the box runs the same
  pipeline and serves the report at /upload/report. The Mac flow below remains
  fully supported. After editing import scripts or payee labels, run
  `scripts/deploy_upload.sh` to sync the box copy.

- Never `git add -f` anything; secrets live in gitignored `.env*` files.
- New accounts appearing in exports fail loudly — add them to `ACCOUNTS` in
  `scripts/import_isbank.py`.
- USD/EUR card statements are imported like TL ones, from print-to-PDF or a
  pasted `.txt`; when both cover one kesim the `.txt` wins.
