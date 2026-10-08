# Two short-call checks, 8 October 2026

Two complete human-spoken simulated banking calls from
[Gridspace-Stanford Harper Valley](https://github.com/cricketclub/gridspace-stanford-harper-valley)
were run once through GTCRN -> Parakeet v2 INT8 CUDA -> Qwen3.5 4B refinement
-> Qwen documentation and validation. Source revision is frozen in the
[actual execution report](../evaluation/results/harper-short-calls.json).
The corpus is attributed to Gridspace and Stanford under CC BY 4.0.

Only the two calls and their annotations were downloaded, plus the repository
file index, README and license. Source WAVs and generated caches remain outside
Git. Synchronized agent/caller channels were averaged at their native 8 kHz
rate, without cropping, trimming or shifts, before normal production resampling
to 16 kHz and enhancement. Every original frame remains represented.

Selection happened before inference: first two lexically sorted call IDs with
equal channel file sizes in the recorded range, then verified 60-120-second
durations. Both have caller and agent MOS labels of 5. No model-result selection,
prompt change, model sweep, reference injection or repeat inference occurred.
The generic title and empty glossary contain no call-specific reference facts.

| Measurement | 01cefd6f5c044a6f | 01f7ec3700424bc0 |
| --- | --- | --- |
| Complete audio duration | 63.00 s | 62.38 s |
| End-to-end Runner time | 63.94 s | 67.83 s |
| Raw full-call WER | 12.00% | 13.51% |
| Refined full-call WER | 12.00% | 13.51% |
| Reference words | 100 | 74 |
| Substitutions / deletions / insertions | 2 / 10 / 0 | 6 / 3 / 1 |
| Final pipeline state | Complete | Complete |
| Summary points | 3 | 3 |
| Fully supported summary claims, provisional review | 2 / 3 | 3 / 3 |
| Generated tasks / decisions | 0 / 0 | 0 / 0 |
| Canonical JSON and ZIP-member parity | Pass | Pass |

WER covers the **entire calls**, with lowercase/punctuation normalization,
apostrophes retained, and annotation-only noise/unknown tags excluded. It does
not expand numbers. The first call's phone number was recognized correctly,
but spoken digits versus `715139-0787` receive word-level errors under this
fixed rule. The second has the same issue for written versus spoken times.
The normalization was not revised after inference to lower the reported WER.
Across 174 reference words there are 22 errors: pooled literal WER is 12.64%.
These are different recordings from AMI, so lower WER does not demonstrate an
improvement to the fixed ES2002a baseline or an enhancement benefit.

## Summary and notes review

The first summary preserves the password-reset request, correct phone digits
and closing statement. One point adds an unstated reason for asking for the
phone number. The second summary preserves the branch-hours request, correct
9:30 a.m.-5 p.m. answer and refusal of further assistance. All three of its
summary claims are supported by the human transcript.

Detailed notes still show weaknesses: invented reasons for collecting contact
information or pausing, and assigning the caller's "Certainly" to the agent.
The first record also introduces unnecessary uncertainty about the two names.
The [review labels](../evaluation/results/harper-short-calls-review.json) record
these findings. They are a provisional agent review, not independent human/audio
adjudication; the minutes flags are not an exhaustive accuracy score.

No explicit future task or meeting decision appears in these simple calls.
Empty task/decision lists are reasonable here, but cannot verify meeting task
recall, owner/deadline extraction or long-meeting consolidation.

## Verification and reproduction

Both genuine executions completed without summary-only fallback. Source hashes,
GTCRN provenance, model identities, actual calls, raw/refined text and generated
records are in the report. WER arithmetic, complete source frame counts/durations,
provider/precision, unchanged refinement and export parity were checked against
saved artifacts. There is no new original-audio control, so no claim about GTCRN
benefit follows from this test. Existing prompts and application code were left
unchanged.

`evaluation/harper.py` reproduces the bounded evaluation when the exact source
files/index exist in `.cache/harper`. It refuses to overwrite a saved report.
Use the existing native CUDA library PATH setup, then run from the repository
root:

```powershell
.venv/Scripts/python.exe evaluation/harper.py
```

The result supports using these short calls for quick transcript/summary checks.
It does not replace AMI meeting-specific evaluation or close Phase 5's accuracy
and unseen-recording gates.
