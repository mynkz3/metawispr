# Meeting notebook redesign

Implemented on 2026-10-08 in the existing React, TypeScript and Vite frontend.
The backend, models, prompts, validation and checkpoint processing are unchanged.

The workspace uses cream and paper surfaces, charcoal outlines, restrained offset
shadows, yellow controls, lavender review notes and a blue evidence panel. Georgia
Italic headings accompany locally bundled Inter Regular body text and controls.
The Inter font is from the Google Fonts Inter distribution, licensed under SIL
OFL 1.1; its license is bundled at `frontend/public/fonts/OFL.txt`. The font source
was the official Google Fonts CSS for `Inter:wght@400`, which supplied the TTF
asset hosted on fonts.gstatic.com. No runtime font service is required.

The compact header exposes the library, focus mode, new recording and available
downloads. Desktop library navigation can collapse; phones use a dismissible
drawer. Focus mode enlarges the record while keeping source audio reachable.
Drawer positioning follows the measured header height, including wrapping on
small screens. Escape dismisses downloads or the library and restores focus.

Upload retains its file picker, drag/drop, actual configured limits, optional
title and glossary. Review retains keyboard tabs, raw/refined transcripts,
correction history, revisions, unspecified assignments, exact source quotes and
audio-window seeking. Partial sections have explicit unavailable messages and
do not display misleading zero-count badges. The validated summary remains
visible. Failed stages retain transcript access and checkpoint retry controls.

## Checks performed

- `npm run build`: TypeScript check and Vite production build passed.
- Six synthetic Playwright checks passed: upload validation and ordered polling;
  desktop review, corrections, keyboard navigation and export links; failures,
  retries and outages; phone review and source playback; desktop upload; library,
  focus mode and partial records.
- Automated axe checks found no WCAG 2 A/AA or WCAG 2.1 AA violations in the tested
  states. Layout checks passed at 1440, 390 and 360 pixel viewport widths.
- Desktop and phone upload/review screenshots were inspected. Synthetic fixture
  content is explicitly identified in its meeting titles. Screenshots remain
  outside Git under `.cache/ui-qa/`.
- A read-only browser check passed against the existing complete Harper Valley
  record `23ca67bf-d815-4ce1-92a6-8ca59ca430e0`: supporting quote, source seek and
  all nine available downloads. Exported meeting JSON matched the saved record.
- The same check passed against the existing authored synthetic partial record
  `04bc934c-61bf-43a3-9400-a00f45020c53`, including unavailable task messaging.
- `git diff --check -- frontend` passed.

The saved-record check is reusable by setting `METAWISPR_REVIEW_ID` and
`METAWISPR_UI_URL`, then running
`npm test -- --grep 'saved pipeline record'` from `frontend/` against a backend
containing that record. Set `PLAYWRIGHT_BROWSERS_PATH` if browsers are stored in
the repository cache. This check does not initiate inference.

The opt-in browser test that uploads audio through installed models was skipped
for this UI change. No ASR/LLM runs, accuracy evaluations or model-quality claims
were added. Browser verification used Chromium; other browser engines were not
tested. Unrelated pre-existing working-tree changes were preserved.
