#!/usr/bin/env node
// Marks folders as trusted for Claude Code, so its "do you trust this folder?" dialog does
// not stop a new session there. Claude Code keeps the answer per folder in ~/.claude.json
// (projects.<absolute path>.hasTrustDialogAccepted). Trusting a folder lets its hooks and MCP
// servers run unasked: use it only for folders you wrote or own, never for a third-party clone.
//
//   trust-claude-folder.mjs <absolute folder> [...]
//
// Prints one line per folder: "trusted <path>" or "already trusted <path>". Exits 1 on a
// path that is not an absolute existing directory. The file is rewritten in one rename.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const file = path.join(os.homedir(), ".claude.json");
const dirs = process.argv.slice(2);
if (!dirs.length) { console.error("usage: trust-claude-folder.mjs <absolute folder> [...]"); process.exit(1); }
for (const d of dirs) {
  if (!path.isAbsolute(d) || !fs.existsSync(d) || !fs.statSync(d).isDirectory()) {
    console.error(`trust-claude-folder: not an existing absolute folder: ${d}`);
    process.exit(1);
  }
}

const config = JSON.parse(fs.readFileSync(file, "utf8"));
config.projects ||= {};
let changed = false;
for (const d of dirs) {
  const dir = fs.realpathSync(d);
  const entry = config.projects[dir] ||= { allowedTools: [] };
  if (entry.hasTrustDialogAccepted) { console.log(`already trusted ${dir}`); continue; }
  entry.hasTrustDialogAccepted = true;
  changed = true;
  console.log(`trusted ${dir}`);
}
if (changed) {
  fs.writeFileSync(`${file}.tmp`, JSON.stringify(config, null, 2));
  fs.renameSync(`${file}.tmp`, file);
}
