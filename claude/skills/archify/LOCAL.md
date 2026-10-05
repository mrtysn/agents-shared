# Local override of upstream archify

`override.patch` carries two local changes on top of `tt-a1i/archify`:

- **Output location** (`SKILL.md`): diagrams default to `$DEV_ROOT/notebook/archify/`.
- **Details on demand**: an optional `detail` (`summary`, `points`, `links`) on every
  node and relationship in all five schemas; `renderers/shared/cli.mjs` collects it,
  `utils.mjs` writes it as `<script id="archify-details-data">` beside the SVG, and
  `assets/template.html` renders it as the lead of the node passport and the pinned
  relationship. Authoring guidance is in the `LOCAL`-fenced parts of `SKILL.md` and
  `references/authoring-contract.md`; tests are in `test/semantic-passport.test.mjs`.
- **Straight links between near-aligned boxes**: `automaticPortSpread` in
  `renderers/shared/geometry.mjs` centres an exclusive bundle (all links between the
  same two boxes on facing sides) on the boxes' shared span, and `alignFacingPorts` in
  `renderers/architecture/routing.mjs` no longer skips authored
  `fromSide`/`toSide`. Tests are in `test/automatic-port-spread.test.mjs`.

## On an upstream sync

- Upstream adds and removes files between releases, which `sync-external-skills.sh`
  does not handle (it only fetches the listed files). Merge in a clone of the release
  tag instead: 3-way `git merge-file` each file (base `.upstream/`, ours the working
  file, theirs the tag), copy new files, drop removed ones, then rewrite `.upstream/`,
  `source.json` `files`/`commit`, and `override.patch` from the result.
- `assets/template.html` is generated upstream from `viewer/` (outside the skill
  directory) by `scripts/generate-viewer.mjs`. Port the details passport there, not
  into the template: the CSS after `.semantic-passport-detail[hidden]` in
  `viewer.css`, the `ARCHIFY:DETAILS_DATA` marker and `#focus-notes` markup in
  `template.source.html`, the `Archify.details` IIFE at the end of
  `motion-governor.js`, and `renderNotes`/`renderRelationshipNotes` plus their calls
  in `focus.js`; then run `npm run generate:viewer` and copy the template back.

- `renderers/shared/generated-validators.mjs` is one minified line, so any upstream
  schema change conflicts there. Never merge it by hand: take upstream's schemas plus
  the `detail` insertions, then regenerate with `npm run generate:validators` in a
  clone of upstream that has its dev dependencies, and copy the file back.
- The bundled `examples/*.html` are re-rendered with the local template, so the golden
  checks compare like with like. After a sync, in the release clone with the merged files
  in place: `npm run render:examples`, `node scripts/render-examples.mjs`, copy
  `../examples/web-app-rendered.html` over `../examples/web-app.html`, rerun the
  Checkout `compare` into `../examples/checkout-platform-delta.{html,receipt.json}`
  (base and head are `examples/checkout-platform.{base,head}.architecture.json`,
  `--quality showcase`), `npm run build:gallery`, `npm run build:readme-showcase`. Only
  the five `examples/*.html` come back into this directory; the rest exist so the suite
  can pass.
- Run the full suite in an upstream clone before copying files back: `npm test` in
  `archify/` after `npm ci`. It passes with no failures.
