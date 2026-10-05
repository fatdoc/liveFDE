# Prototype Instructions

Run the local server yourself and open the preview in the browser available to this environment. Do not give the user server-start instructions when you can run it.

Before making substantial visual changes, use the Product Design plugin's `get-context` skill when the visual source is unclear or no longer matches the current goal. When the user gives durable prototype-specific design feedback, preferences, or decisions, record them in `AGENTS.md`.

When implementing from a selected generated mock, treat that image as the source of truth for layout, component anatomy, density, spacing, color, typography, visible content, and hierarchy.

Build app UI in `src/`. Keep `.openai/hosting.json`, `worker/index.js`, `scripts/prepare-sites-build.mjs`, and `tests/sites-worker.test.mjs` intact so the same local prototype can be handed to Sites. Before a Sites handoff, run `npm run build` and `npm run test:sites`; the build must leave `dist/client/index.html`, `dist/server/index.js`, and `dist/.openai/hosting.json`.

## Current user direction — 2026-10-05

This directory is the React + TypeScript interactive prototype. Reproduce all navigation pages, not only the four reference images. The final system direction is Python/FastAPI + React + PostgreSQL, independently deliverable without CPB services. Scoring dimensions, weights and evidence rules are pending: never fabricate them. Keep original wording, teaching notes and adapted scripts distinct; only approved assets enter the learning library. Current demo state is in-memory and explicitly labeled.

## Summary report direction — 2026-10-05

The user supplied `路演评分报告_会议3 (13).pdf` as a structural reference and explicitly has no settled standard. Keep `/reports` as an editable draft template for single-session and weekly summaries. Reuse summary/evidence/problem/action organization only; do not import competition scores, speech thresholds, invented effects or inferred long-term portraits. `docs/summary-report-template.md` records this distinction.
