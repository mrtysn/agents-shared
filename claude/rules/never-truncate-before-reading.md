# Never open a file for writing before reading it

**An existing file is changed with the Edit tool, or read into memory first and
written back from that copy — never in one expression that opens it for writing and
reads it** (`open(p, "w")…open(p).read()`, `sed … f > f`): the open empties the file
before the read runs.

The full rule appears the first time a session runs such a command.

Provenance: [docs/provenance/never-truncate-before-reading.md](../../docs/provenance/never-truncate-before-reading.md).
