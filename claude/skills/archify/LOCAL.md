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
  `renderers/architecture/render-architecture.mjs` no longer skips authored
  `fromSide`/`toSide`. Tests are in `test/automatic-port-spread.test.mjs`.

## On an upstream sync

- `renderers/shared/generated-validators.mjs` is one minified line, so any upstream
  schema change conflicts there. Never merge it by hand: take upstream's schemas plus
  the `detail` insertions, then regenerate with `npm run generate:validators` in a
  clone of upstream that has its dev dependencies, and copy the file back.
- The bundled `examples/*.html` are kept at upstream's bytes on purpose; regenerating
  them would put the whole template into the patch once per example. Upstream's golden
  test is the only consumer, and it cannot run in this vendored layout.
- Run the full suite in an upstream clone before copying files back: `npm test` in
  `archify/` after `npm ci`.
