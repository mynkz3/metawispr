# Metawispr development rules

Read `docs/DESIGN.md` and `docs/PHASES.md` before changing the application.

- Implement the recorded English meeting workflow required by the problem statement.
- Preserve raw ASR output. Refined text must have a recorded edit history.
- Keep transcription, refinement, and documentation as distinct ordered stages.
- Never invent decisions, owners, deadlines, benchmark results, or model outputs.
- Generate every export from the same validated meeting record.
- Run checks appropriate to each change. Record what was actually tested.
- Make a local Git commit after each completed phase or coherent change/fix, as requested by the owner. Do not bundle unrelated changes. Never commit recordings from users, secrets, model weights, generated caches, or environment directories.
- A commit is not a push. Push only when the owner requests it.
- Favor ordinary functions, standard-library storage, and a small dependency set.
- Keep future live capture, diarization, cloud hosting, accounts, and integrations out of the initial release.
