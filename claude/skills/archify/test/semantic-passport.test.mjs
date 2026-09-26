import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const skillRoot = path.resolve(__dirname, '..');
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'archify-semantic-passport-'));

const CASES = {
  architecture: 'web-app.architecture.json',
  workflow: 'agent-tool-call.workflow.json',
  sequence: 'cache-miss-request.sequence.json',
  dataflow: 'product-analytics.dataflow.json',
  lifecycle: 'agent-run.lifecycle.json',
};

function render(mode, example) {
  const output = path.join(tmp, `${mode}.html`);
  execFileSync(process.execPath, [
    path.join(skillRoot, `renderers/${mode}/render-${mode}.mjs`),
    path.join(skillRoot, 'examples', example),
    output,
  ]);
  return fs.readFileSync(output, 'utf8');
}

function svg(html) {
  return html.match(/<svg\b[\s\S]*?<\/svg>/)?.[0] || '';
}

test('all typed renderers emit details-on-demand metadata and native SVG titles', () => {
  for (const [mode, example] of Object.entries(CASES)) {
    const html = render(mode, example);
    const diagram = svg(html);
    assert.match(diagram, /data-node-kind="[^"]+"/, mode);
    assert.match(diagram, /data-node-sublabel="[^"]+"/, mode);
    assert.match(diagram, /data-node-context="[^"]+"/, mode);
    assert.match(diagram, /<g id="node-[^"]+"[\s\S]*?<title>[^<]+ · [^<]+<\/title>/, mode);
  }
});

test('renderer-owned structure supplies truthful Semantic Passport context', () => {
  const architecture = render('architecture', CASES.architecture);
  const workflow = render('workflow', CASES.workflow);
  const sequence = render('sequence', CASES.sequence);
  const dataflow = render('dataflow', CASES.dataflow);
  const lifecycle = render('lifecycle', CASES.lifecycle);

  assert.match(architecture, /data-node-id="api"[^>]+data-node-kind="backend"[^>]+data-node-context="AWS Region: us-west-2 › sg-api :443\/:8000"/);
  assert.match(workflow, /data-node-id="approval"[^>]+data-node-kind="security"[^>]+data-node-context="Policy &amp; Recovery › Human or policy stop › Plan \+ route"/);
  assert.match(sequence, /data-node-id="redis"[^>]+data-node-kind="database"[^>]+data-node-context="Sequence participant"/);
  assert.match(dataflow, /data-node-id="warehouse"[^>]+data-node-kind="database"[^>]+data-node-context="04 \/ Store"/);
  assert.match(lifecycle, /data-node-id="executing"[^>]+data-node-kind="active"[^>]+data-node-context="Lifecycle phases"/);
});

test('Relationship Lens renders one Semantic Passport and copyable stable focus link', () => {
  const html = render('workflow', CASES.workflow);
  assert.match(html, /<span class="relationship-lens-eyebrow">Semantic passport<\/span>/);
  assert.match(html, /id="focus-detail" hidden/);
  assert.match(html, /id="focus-kind" data-passport="kind"/);
  assert.match(html, /id="focus-context" data-passport="context" hidden/);
  assert.match(html, /id="focus-tag" data-passport="tag" hidden/);
  assert.match(html, /id="focus-id" data-passport="id"/);
  assert.match(html, /id="btn-focus-clear"[^>]+aria-label="Close semantic passport"[^>]+title="Close">&#215;<\/button>/);
  assert.match(html, /id="btn-focus-copy"[^>]+aria-label="Copy link to focused node"/);
  assert.match(html, /id="btn-focus-relations"[^>]+aria-expanded="false"[^>]+aria-controls="relationship-lens-list"/);
  assert.match(html, /function renderPassport\(id, node\)/);
  assert.match(html, /var relationId = record && record\.id/);
  assert.match(html, /\? '#relation=' \+ encodeURIComponent\(relationId\)/);
  assert.match(html, /: '#focus=' \+ encodeURIComponent\(activeIds\[0\]\)/);
  assert.match(html, /navigator\.clipboard\.writeText\(value\)/);
  assert.match(html, /document\.execCommand\('copy'\)/);
  assert.match(html, /copyLink: copyFocusLink/);
  assert.match(html, /compactOnMobile = mobile && chip\.getAttribute\('data-relations-expanded'\) !== 'true'/);
  assert.match(html, /nodeTop - chip\.offsetHeight - gap/);
  assert.match(html, /focus-chip:not\(\[data-relations-expanded="true"\]\) \.relationship-lens-list \{ display: none; \}/);
  assert.match(html, /clearBtn\.addEventListener\('click', function \(\) \{ clear\(\{ restoreFocus: true \}\); \}\)/);
  assert.match(html, /chip\.hidden \|\| !target \|\| typeof target\.closest !== 'function' \|\| chip\.contains\(target\)/);
  assert.match(html, /target\.closest\('\[data-node-id\], \[data-relationship-hit-key\], \.overview-map'\)/);
  assert.match(html, /document\.addEventListener\('click',[\s\S]+?clear\(\);\s+\}, true\);/);
  assert.match(html, /Archify\.focus\.clear\(\{ restoreFocus: true \}\)/);
});

test('Node Finder searches and presents the same passport facts', () => {
  const html = render('dataflow', CASES.dataflow);
  assert.match(html, /var authored = node\.getAttribute\('data-node-kind'\)/);
  assert.match(html, /var sublabel = node\.getAttribute\('data-node-sublabel'\) \|\| ''/);
  assert.match(html, /var context = node\.getAttribute\('data-node-context'\) \|\| ''/);
  assert.match(html, /var tag = node\.getAttribute\('data-node-tag'\) \|\| ''/);
  assert.match(html, /search: \(id \+ ' ' \+ label \+ ' ' \+ type \+ ' ' \+ sublabel \+ ' ' \+ context \+ ' ' \+ tag \+ ' ' \+ sourceSearch \+ ' ' \+ text\)\.toLowerCase\(\)/);
  assert.match(html, /\[viewerKindLabel\(item\.type\), item\.id, item\.sublabel, item\.tag\]\.filter\(Boolean\)\.join\(' \\u00b7 '\)/);
  assert.match(html, /meta\.title = \[viewerKindLabel\(item\.type\), item\.id, item\.context, item\.sublabel, item\.tag\]\.filter\(Boolean\)\.join\(' \\u00b7 '\)/);
});

process.on('exit', () => fs.rmSync(tmp, { recursive: true, force: true }));

const DETAIL_COLLECTIONS = {
  architecture: ['components', 'connections'],
  workflow: ['nodes', 'edges'],
  sequence: ['participants', 'messages'],
  dataflow: ['nodes', 'flows'],
  lifecycle: ['states', 'transitions'],
};

function renderAuthored(mode, diagram, name) {
  const input = path.join(tmp, `${name}.json`);
  const output = path.join(tmp, `${name}.html`);
  fs.writeFileSync(input, JSON.stringify(diagram));
  execFileSync(process.execPath, [path.join(skillRoot, `renderers/${mode}/render-${mode}.mjs`), input, output], { stdio: 'pipe' });
  return fs.readFileSync(output, 'utf8');
}

test('authored details travel beside the SVG, keyed by node id and relationship key', () => {
  for (const [mode, example] of Object.entries(CASES)) {
    const [nodeCollection, relationCollection] = DETAIL_COLLECTIONS[mode];
    const diagram = JSON.parse(fs.readFileSync(path.join(skillRoot, 'examples', example), 'utf8'));
    const plain = renderAuthored(mode, diagram, `${mode}-plain`);
    const node = diagram[nodeCollection][0];
    const lastIndex = diagram[relationCollection].length - 1;
    const relation = diagram[relationCollection][lastIndex];
    node.detail = { summary: `Why ${node.id} exists`, points: ['Owns one fact'], links: [{ label: 'Open inside', href: `inner.html#focus=${node.id}` }] };
    relation.detail = { summary: 'What crosses this edge' };
    const html = renderAuthored(mode, diagram, `${mode}-detail`);

    assert.equal(svg(html), svg(plain), `${mode}: details must not change the canonical SVG`);
    assert.doesNotMatch(plain, /id="archify-details-data"/, `${mode}: no blob without authored details`);
    const blob = JSON.parse(html.match(/<script id="archify-details-data" type="application\/json">([^<]*)<\/script>/)[1]);
    assert.deepEqual(blob.nodes[node.id], node.detail, mode);
    assert.deepEqual(blob.relationships[String(lastIndex)], relation.detail, mode);
    const keyed = new RegExp(`data-edge-from="${relation.from}" data-edge-to="${relation.to}"[^>]*data-edge-key="${lastIndex}"`);
    assert.match(svg(html), keyed, `${mode}: relationship key must match authored index`);
  }
});

test('detail links reject script and data URLs at validation time', () => {
  const diagram = JSON.parse(fs.readFileSync(path.join(skillRoot, 'examples', CASES.architecture), 'utf8'));
  diagram.components[0].detail = { links: [{ label: 'x', href: 'javascript:alert(1)' }] };
  assert.throws(() => renderAuthored('architecture', diagram, 'architecture-bad-link'), /must match pattern/);
});

test('viewer renders authored details as the passport lead and demotes metadata', () => {
  const html = render('architecture', CASES.architecture);
  assert.match(html, /<div class="semantic-passport-notes" id="focus-notes" hidden/);
  assert.match(html, /Archify\.details = \(function/);
  assert.match(html, /\.focus-chip\[data-has-notes="true"\] \.semantic-passport-meta/);
  assert.match(html, /function safeHref\(href\)/);
});
