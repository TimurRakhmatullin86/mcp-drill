# mcp-drill npm split plan — deferred until traction

**Status 2026-09-07:** PyPI 0.0.1 live (20KB whl), npm shim `mcp-drill@0.0.1` live (stub that points to PyPI), GitHub Action `action.yml` at repo root already gives a separate GitHub marketplace entry. The mandate's "split into 3 npm packages" is understood, but doing it at 0 stars / 6 downloads/week would dilute effort and looks like a farm to GitHub/USCIS.

## Current state (honest)

- `mcp-drill` on npm: 13.5 kB, bin `mcp-drill` that prints version + points to PyPI (`pipx install mcp-drill`). Provenance: `pkg.tgz` has 4 files (LICENSE, README, package.json, bin/mcp-drill.js). This is deliberate — the real CLI is Python, npm is just a shim for `npx` discoverability.
- `action.yml` at repo root: users consume as `uses: TimurRakhmatullin86/mcp-drill@v0` — GitHub indexes this as a GitHub Action, not an npm dependent. That's fine; Actions marketplace is stronger signal than a fake npm package.
- No `mcp-drill-report` yet — scorecard HTML is `docs/index.html` generated from `studies/pilot/results.json`; no standalone JS.

## When to split (trigger: 1 of these)

- GitHub stars >200 and first external issue/PR from a stranger, OR
- PyPI downloads >1k/week for 2 consecutive weeks, OR
- At least 1 company says "we use mcp-drill in CI" — then split to optimize for that use case.

## Split design (when triggered)

```
own/mcp-drill/
  packages/
    mcp-drill-runner/      # npm CLI that shells out to python -m mcp_drill or bundles via pkg
      package.json { name: "mcp-drill-runner", bin: { "mcp-drill": "dist/index.js" } }
      src/index.ts — spawn python -m mcp_drill with --faults passthrough, fallback if python missing
    mcp-drill-action/      # standalone Action repo OR composite at packages/mcp-drill-action/action.yml
      action.yml — thin wrapper around pip install mcp-drill[scan] + gate.py
      marketplace: publish as TimurRakhmatullin86/mcp-drill-action for separate marketplace entry
    mcp-drill-report/      # HTML scorecard renderer (pure JS, no python)
      package.json { name: "mcp-drill-report", bin: { "mcp-drill-report": "bin/report.js" } }
      src/report.ts — reads mcp-drill.json, emits docs/index.html + badge.json (replaces python batch)
```

Each gets:
- Apache-2.0, semver, no telemetry, own README with 1-command install, own CI, own tests
- `files` minimal, engines node>=18, keywords mcp, testing, etc.
- Published to npm under TimurRakhmatullin86 scope — gives 3 separate `Used by` signals on GitHub (npm dependents scan package-lock.json). GitHub Action's `Used by` is separate marketplace metric.

## Why not now

- **Ghost Town risk** (STRATEGY §4): 3 packages × 0 dependents = looks like repo farm, triggers GitHub manufacturing flag and USCIS "project factory" discount. Better 1 solid package with 500 dependents than 3 with 0.
- **Maintenance cost**: 3 × README + CI + releases = 6.5h/week × 3 = 19.5h/week for 0 gain. Current funnel says 1 active project at a time.
- **Signal:** For EB1A, PyPI `Used by` + `downloads` (Tier 2) outweighs npm `Used by` (Tier 3) for a Python tool. PyPI just went live — nurture it first (awesome-list, article, SO answers).

## Immediate next steps instead (0₽, higher leverage)

1. Awesome PRs (done punkpeye #13824, wong2 needs mcpservers.org submit)
2. VS page live (done docs/vs-mcp-scan)
3. Article dev.to + hashnode (draft at ARTICLE-dev.to.md — publish + HN/Reddit + 10 outreach emails as per STRATEGY §7)
4. StackOverflow answers: find 5 questions about "MCP outputSchema validation" and answer with `pip install mcp-drill`
5. After 100 stars: re-evaluate split, start with `mcp-drill-report` (pure JS, easiest to justify as standalone).

## Evidence to capture before split

- Screenshot `Used by` on PyPI (pypistats) and npm after month of traction
- Screenshot GitHub Dependents for main repo after first external dependent appears
- Keep `npm view mcp-drill --json` and `curl https://pypi.org/pypi/mcp-drill/json` snapshots in `~/eb1-portfolio/evidence/mcp-drill/` with dates

If you want me to scaffold the 3 packages now anyway (empty dirs + package.json stubs), say "scaffold npm split" and I'll create them behind a feature flag without publishing.
