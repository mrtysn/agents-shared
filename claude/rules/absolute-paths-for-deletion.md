# Deletions name their targets by absolute path

**Every `rm`, `rmdir`, `unlink` and `trash` operand must be a full path.** No
relative paths, no globs, no unresolved variables or `$(…)`, never `/` or a
top-level directory, and no `find … -delete` or `xargs rm`. A hook blocks each of
these. The full rule appears the first time a session deletes something.
