# Game harness — browser games (three.js, Phaser, PixiJS, plain canvas)

How each of the five parts is built for a game that runs in a browser tab. Playwright is the
driver; Vitest or the project's unit runner covers determinism and coordinate math separately.

## 1. State hook: one global

Expose a single object on `window`. Tests read it with `page.evaluate`; a human reads it in the
console.

```ts
// src/debug/hook.ts — imported once at boot
declare global { interface Window { __GAME__: GameHook } }

window.__GAME__ = {
  ready: false,                       // flips true when the scene and streamed content are in
  state: () => ({
    mode: game.mode,
    near: game.nearestBody()?.name ?? null,
    camera: game.activeCamera.name,
    playerPos: game.player.position.toArray(),
    streamingReady: game.terrain.ready(),
  }),
  counters: () => ({
    drawCalls: renderer.info.render.calls,      // three.js; use the renderer's own stats elsewhere
    triangles: renderer.info.render.triangles,
    geometries: renderer.info.memory.geometries,
    textures: renderer.info.memory.textures,
    queuedJobs: game.terrain.queued(),          // worker jobs still pending
    bufferedBytes: game.terrain.bufferedBytes(),
  }),
}
```

Data only. Add fields as the game grows.

## 2. Named scenes: query parameters

The boot code reads the URL and starts from the requested scene, seed and clock mode.

```text
http://localhost:5173/?scene=orbit&seed=42&fixedStep=1
```

`scene` selects a starting definition from `tests/scenes/` (position, mode, loadout).
`seed` seeds every random source. `fixedStep=1` makes the game loop advance a constant
delta per frame instead of reading the wall clock, which is the condition for repeatable
captures. Everything animated must read the game's clock, not `performance.now()` or
`Date.now()`; grep for both and remove them from anything that draws.

## 3. Headless capture: Playwright, fresh context per shot

```ts
// tests/capture/shots.spec.ts
import { test, expect } from '@playwright/test'

const SHOTS = ['orbit', 'pulse_travel', 'descent', 'coastal_landing']

for (const scene of SHOTS) {
  test(`shot ${scene}`, async ({ browser }) => {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1 })
    const page = await ctx.newPage()
    await page.goto(`/?scene=${scene}&seed=42&fixedStep=1`)
    await page.waitForFunction(() => window.__GAME__?.ready === true, null, { timeout: 30_000 })
    await page.evaluate(() => new Promise(r => { let n = 0; const f = () => (++n < 30 ? requestAnimationFrame(f) : r(null)); f() }))
    await expect(page).toHaveScreenshot(`${scene}.png`, { maxDiffPixels: 0 })
    await ctx.close()
  })
}
```

`toHaveScreenshot` writes the baseline on first run and fails on any pixel change after; the
baseline is updated deliberately with `--update-snapshots` once a change is accepted. A new
context per shot is what stops particle age, exposure and streaming state leaking between
captures. A fixed frame count after `ready` puts every shot at the same simulation time.

For an effect-isolating capture, add a query flag the game honours (`&mask=0`) and shoot the
same scene with it on and off; the diff shows exactly what the effect changes.

## 4. Journey tests: real controls, recorded state

```ts
// tests/journeys/land.spec.ts
test('descend, land, exit, walk, reboard', async ({ page }) => {
  await page.goto('/?scene=coastal_approach&seed=42')
  await page.waitForFunction(() => window.__GAME__?.ready === true)
  const trace: any[] = []
  const sample = async () => trace.push(await page.evaluate(() => window.__GAME__.state()))

  await page.keyboard.down('KeyS')                       // the game's own descend binding
  for (let i = 0; i < 120 && (await page.evaluate(() => window.__GAME__.state().mode)) !== 'landed'; i++) {
    await page.waitForTimeout(50); await sample()
  }
  await page.keyboard.up('KeyS')

  expect(trace.at(-1).mode).toBe('landed')
  expect(await page.evaluate(() => window.__GAME__.state().streamingReady)).toBe(true)
  for (let i = 1; i < trace.length; i++) {               // no teleport during the transition
    const [a, b] = [trace[i - 1].playerPos, trace[i].playerPos]
    expect(Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2])).toBeLessThan(5)
  }
  await test.info().attach('trace', { body: JSON.stringify(trace), contentType: 'application/json' })
})
```

One journey per interaction the game promises. They assert on state and run in the normal
Playwright headless mode; pixels are not involved.

## 5. Measured runs: frame intervals with percentiles

```ts
// tests/profile/orbit.spec.ts
test('orbit frame intervals', async ({ page }) => {
  await page.goto('/?scene=orbit&seed=42')             // no fixedStep: real timing
  await page.waitForFunction(() => window.__GAME__?.ready === true)
  const ms: number[] = await page.evaluate(() => new Promise(res => {
    const out: number[] = []; let last = performance.now()
    const f = () => { const t = performance.now(); out.push(t - last); last = t; out.length < 90 ? requestAnimationFrame(f) : res(out) }
    requestAnimationFrame(f)
  }))
  ms.sort((a, b) => a - b)
  const p = (q: number) => ms[Math.floor(q * (ms.length - 1))]
  const counters = await page.evaluate(() => window.__GAME__.counters())
  console.log(JSON.stringify({ p50: p(0.5), p95: p(0.95), p99: p(0.99), worst: ms.at(-1), ...counters }))
})
```

Headless Chromium renders with a software rasteriser unless the GPU is enabled, so these
numbers compare one build against another on the same machine; they are not the frame rate
the author sees. Say so when reporting them. For device numbers run the same scene headed on
the target machine at its real device pixel ratio, since a Retina viewport renders more than
three times the pixels of the headless default.

## Workers and stalls

Generation belongs in Web Workers, and the state hook reports what is queued and buffered so a
stall can be attributed to streaming rather than rendering. Any fallback generation on the
main thread must be resumable, spending a few milliseconds per frame and yielding, or every
capture and profile run stalls with it. Shader compilation that happens lazily mid-play shows
up as p99 spikes with no counter change; pre-warm the materials at boot and confirm with the
profile run that the spikes are gone.
