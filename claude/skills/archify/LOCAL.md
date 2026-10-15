# Local override of upstream archify

`override.patch` carries three local changes on top of `tt-a1i/archify`:

- **Output location** (`SKILL.md`): diagrams default to `$DEV_ROOT/notebook/archify/`.
- **Details on demand**: an optional `detail` (`summary`, `points`, `links`) on every
  node and relationship in the architecture, workflow, sequence, dataflow, lifecycle,
  erd, class and tree schemas (timeline events and waterfall spans already have an
  upstream string `detail`, so they get none); `renderers/shared/cli.mjs` collects
  object-valued `detail` only, `utils.mjs` writes it as
  `<script id="archify-details-data">` beside the SVG, and `assets/template.html`
  renders it as the lead of the node passport and the pinned relationship. Authoring
  guidance is in the `LOCAL`-fenced parts of `SKILL.md` and
  `references/authoring-contract.md`.
- **Straight links between near-aligned boxes**: `automaticPortSpread` in
  `renderers/shared/geometry.mjs` centres an exclusive bundle (all links between the
  same two boxes on facing sides) on the boxes' shared span, and architecture's
  `alignFacingPorts` in `renderers/architecture/routing.mjs` passes
  `alignExplicitSides: true` to the shared `alignAutomaticFacingPorts`, so authored
  `fromSide`/`toSide` are aligned too (dataflow keeps upstream behaviour).

`local/` is ours alone and never listed in `source.json`:

- `local/tests/semantic-passport.test.mjs`, `local/tests/automatic-port-spread.test.mjs`
  — upstream's tests of the same names plus the local cases. Since 3.1.0 upstream keeps
  its tests in the repository's root `test/`, outside the skill directory, so these are
  written for that location (`skillRoot` is `../archify`).
- `local/port-viewer.py` — ports the details passport into upstream's `viewer/` sources.

## On an upstream sync

- Upstream adds and removes files between releases, which `sync-external-skills.sh`
  does not handle (it only fetches the listed files). Merge in a shallow clone of the
  release tag instead (tags are named `vX.Y.Z`; a full-history clone is over 600 MB):
  3-way `git merge-file` each file that differs between `.upstream/` and the working
  copy (base `.upstream/`, ours the working file, theirs the tag), copy new files, drop
  removed ones, then rewrite `.upstream/`, `source.json` `files`/`commit`, and
  `override.patch` (diff `.upstream` → working, per listed file) from the result.
- Merge `local/tests/*` the same way against the tag's root `test/` files, with the
  previous release's root test as base, and copy them into the clone's `test/`.
- `assets/template.html` is generated upstream from `viewer/` (outside the skill
  directory) by `scripts/generate-viewer.mjs`. Port the details passport there, not
  into the template: `python3 -I local/port-viewer.py <current local
  assets/template.html> <clone>/viewer` inserts the CSS after
  `.semantic-passport-detail[hidden]` in `viewer.css`, the `ARCHIFY:DETAILS_DATA`
  marker and `#focus-notes` markup in `template.source.html`, the `Archify.details`
  IIFE at the end of `motion-governor.js`, and `renderNotes`/`renderRelationshipNotes`
  plus their calls in `focus.js`. Each anchor must occur once or it stops. Then run
  `npm run generate:viewer` in `archify/` and copy the template back.
- `renderers/shared/generated-validators.mjs` is one minified line, so any upstream
  schema change conflicts there. Never merge it by hand: take upstream's schemas plus
  the `detail` insertions, then regenerate with `npm run generate:validators` in the
  clone after `npm ci` in both the root and `archify/`, and copy the file back.
- The bundled `examples/*.html` are re-rendered with the local template, so the golden
  checks compare like with like. In the clone with the merged files in place, from
  `archify/`: `npm run render:examples`, `node scripts/render-examples.mjs`, copy
  `../examples/web-app-rendered.html` over `../examples/web-app.html`, rerun the
  Checkout `compare` into `../examples/checkout-platform-delta.{html,receipt.json}`
  (base and head are `examples/checkout-platform.{base,head}.architecture.json`,
  `--quality showcase`), `npm run build:gallery`, `npm run build:readme-showcase`. Only
  the `archify/examples/*.html` come back into this directory; the rest exist so the
  suite can pass.
- `archify.zip` at the clone root must carry the local `SKILL.md`, or
  `skill-installation.test.mjs` fails ("rebuild archify.zip when Skill instructions
  change"). `scripts/build-zip.sh` refuses any Node but 22 with zlib 1.3.1-e00f703; when
  that is not installed, update the one entry in place: copy `SKILL.md` to
  `<tmp>/archify/SKILL.md` and run `zip -X <clone>/archify.zip archify/SKILL.md` from
  `<tmp>`.
- Run the full suite in the clone root before copying files back:
  `ARCHIFY_CHROME=<Chrome binary> npm run test:full` (headless; without
  `ARCHIFY_CHROME` the browser cases are skipped). `npm test` alone runs only the core
  smoke test. Only the canonical-ZIP cases stay skipped off Node 22.
