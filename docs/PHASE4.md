# Phase 4: review workspace

## Implementation plan

Build one React + TypeScript workspace served by the existing local FastAPI process. Use Vite, plain CSS and ordinary hooks/fetch; no UI framework, router or client state library is needed. The existing API and validated artifacts remain the source of truth.

1. **Upload and local library.** Add a keyboard-accessible file picker and drop area, optional title and glossary, actual upload limits/readiness, recent recordings and a shareable local `?meeting=UUID` selection. Empty states contain no fictional meetings.
2. **Processing and recovery.** Show ordered preparation/transcription/refinement/documentation stages without estimated completion percentages. Poll only active jobs, cancel stale requests when switching meetings, expose setup failures and retry eligible jobs. Preserve access to finished transcripts when later stages fail.
3. **Evidence review.** Provide overview, decisions, tasks and transcript views. Source buttons reveal exact quotes and seek the prepared audio to the segment's coarse window. Raw/refined text, accepted/rejected corrections and revision history remain inspectable. Missing owners/deadlines read “Unspecified.” Results are ready for human review, not certified interpretations.
4. **Exports and delivery.** Download the canonical Markdown, JSON, ZIP and transcript artifacts. Mount the production build after API routes, retaining one-process same-origin deployment. Add frontend lockfile, build instructions and meaningful API/static/browser checks.

## Visual and interaction requirements

Use the design's warm ivory canvas, white surfaces, charcoal text and coral accent, with a 224-pixel desktop rail and a restrained serif display heading. Stack below 900 pixels. Use real audio controls rather than decorative waveforms. Keep technical setup commands in optional setup details. Use semantic controls, visible focus, at least 44-pixel interactive targets, labelled fields, live status/error announcements and reduced-motion support. Render all transcript/model text as text, never as HTML.

Task completion and transcript editing require versioning and invalidation rules; this phase is a read-only review workspace with exports. Live capture, diarization, accounts and public hosting remain future work.

## Exit checks

- Locked frontend installation, TypeScript check and production build succeed.
- Existing backend checks pass; static hosting does not shadow API routes.
- Headless browser checks cover upload, stage transitions, failure/retry, null task fields, transcript/audit inspection, source/audio navigation and downloads. Test fixtures are explicitly synthetic and separate from product data.
- Inspect saved desktop and narrow screenshots; check overflow, keyboard navigation, accessibility and browser errors.
- Open a genuine saved three-model record through the built UI and run one real synthetic upload through the browser/API pipeline. Compare downloaded canonical exports.
- Record actual results below, commit the completed phase and push to the owner's repository. Representative model-quality evaluation remains Phase 5.

## Verification log

5 October 2026. Implemented and verified against the installed local runtime.

- Locked installation `npm ci` succeeded. Node 24.18.0, npm 11.16.0; React 19.3.0, Vite 8.3.2, TypeScript 7.0.2, Playwright 1.63.0 and axe 4.13.0 are recorded in `frontend/package-lock.json`. The production TypeScript check/build succeeded (approximately 76 KB gzip JavaScript and 4.7 KB gzip CSS).
- `python -m unittest discover -s tests -q`: **71 passed**. Two added checks verify static assets, API priority, missing-path/traversal handling and actionable missing-build setup. Backend compilation, `uv sync --locked --offline`, lock consistency and whitespace checks passed.
- `npm test` with both real-smoke environment variables: **6 passed**. Five use explicitly synthetic HTTP fixtures; one uses the genuine local server, installed models and authored speech. Checks cover empty/invalid upload, actual form fields, ordered polling, retry, completed transcript access after failure, outage/reload, null task fields, exact raw markup as text, correction/revision audit, keyboard tab navigation, source focus/audio seek and download controls. Native downloads bypass Playwright page-route fixtures, so fixture tests assert canonical link paths; actual downloaded bytes are checked against the genuine server.
- axe checks reported **zero violations** for the selected WCAG 2 A/AA and 2.1 AA rules on desktop upload/review, phone upload/review and the genuine saved record. Keyboard checks cover arrow/Home tab selection and Escape closing the export menu with focus restoration. This is automated coverage, not a manual screen-reader or complete accessibility certification.
- Inspected full-page screenshots at 1440×1000 and 390×844. No horizontal overflow at those sizes; an additional 360-pixel width check passed. Screenshots live in ignored `.cache/ui-qa/`. The layout stacks content/audio, retains readable unspecified fields and reaches source audio after a phone source selection. A low-contrast decorative label and premature/non-range audio fixture behavior were corrected during checks. The player waits for seekable media before applying a pending source seek.
- The final browser uploaded the 14.997-second authored synthetic meeting from PHASE2.md. Actual saved UUID: `dbb5606c-b5e3-412c-b57a-a226b680d039`, total upload-to-completion about **45.9 s** on the development laptop. Real Parakeet, Qwen3.5 4B and Qwen3.5 9B produced the Docker release decision and Maya/Friday task. No agreed tomorrow deployment was invented. The browser downloaded canonical meeting JSON, compared it to the detail API, opened the exact Docker source quote and loaded the prepared audio. Actual ZIP JSON and Markdown matched their endpoints as well. Additional reruns of the same tiny sample during UI fixes are compatibility repetitions, not independent quality samples.
- Models unloaded after processing. Static hosting uses the existing loopback server; no external fonts, cloud model endpoint or additional product service was introduced. The workspace contains no embedded sample meetings.

## Remaining scope

The workspace is read-only: inspect sources and exports rather than mutate task completion or transcripts without versioning. Times remain coarse audio windows. Matching quotes and successful structured validation still need human interpretation review. Phase 5 remains open for representative and held-out English meetings, model comparison, quality/runtime measurements and release/demo packaging. No accuracy, universal superiority or production-readiness claim follows from the synthetic checks.

Primary frontend references: [React documentation](https://react.dev/learn), [Vite guide](https://vite.dev/guide/), [Playwright test configuration](https://playwright.dev/docs/test-configuration).
