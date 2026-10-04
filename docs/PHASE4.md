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

Implementation and checks pending.
