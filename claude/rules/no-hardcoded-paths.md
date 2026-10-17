# No hardcoded paths

**No absolute or machine-specific path may be committed to a repo or a config.**
Real paths live in a gitignored local file beside a committed `.example`; committed
code reads it and fails with a clear message when a value is missing.

The full rule appears the first time a write contains a home-directory path.
