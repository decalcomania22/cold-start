Put the transcripts of your sessions with Claude, Codex, Cursor, ChatGPT or any other AI tool here:
exported chats, copied text or screenshots. Using AI is expected. We read these to see how you work,
not to count how much you used it.
# Session (Claude Code): rate limits, batched loop pass, model comparison

## Goal
Stop hitting the provider rate limit, raise the dev score, compare models.

## Baseline (dev, `python check.py data/dev output.json`)
| run | circles | orgs | chats | loops found | loops closed | total /56 |
|---|---|---|---|---|---|---|
| rules only (before) | 9.4 | 3.1 | 7.6 | 3.6 | 1.5 | 25.2 |
| old LLM pass (~640 small calls logged in usage.jsonl) | 9.4 | 3.1 | 7.6 | 3.4 | 2.3 | 25.8 |

## Why the rate limit was hit
The old pass sent one call per 40-message chunk of every chat with a keyword hit (up to 67 calls per
run, ~640 calls across runs), with 1 worker and a client that gave up after the second 429.

## Changes
1. `llm.py`: shared client-side pacing (`LLM_RPM`, default 12/min), waits for `Retry-After` or Gemini's
   `retryDelay`, switches to `LLM_FALLBACK_MODEL` on repeated or daily 429s, fails fast on TLS/DNS
   errors, and keeps a disk cache (`.llm_cache/`, `LLM_CACHE=0` disables) so dev re-runs cost nothing.
   Optional `LLM_REASONING_EFFORT`.
2. Loop pass: only chats Arjun takes part in. Quiet 1:1s keep only their last 25 messages; busy chats
   where he sends under 8% of messages keep only ±6 messages around his involvement. Chats are packed
   into ~30k-character batches: 7 calls for the whole dev set (was 67+).
3. Candidate lines (regex: requests, promises, dates, questions) are marked `>>`, and the model must
   rule on each one. That raised recall from 10 to 31 of the 63 answer sources.
4. The model rates each loop 1-3. Only weight 3 is kept, and group chats are dropped (2 hits in 88
   group proposals).
5. Rule loops (spouse requests, ~31% precision) are merged with the LLM loops. A batched status-judge
   call decides how the rule loops ended.
6. `credible_closer`: a bare "ok"/"sure" never closes a loop. A closer from someone other than Arjun
   must say something like done/paid/received/called. A done with no cited message stays open.
7. Office workspace organisation for staff saved as "... Office" (+1.2 orgs). Tagging colleagues by
   company name was tried and lowered the score, so it is off.

## After
| run | circles | orgs | chats | loops found | loops closed | total /56 |
|---|---|---|---|---|---|---|
| rules only | 9.4 | 4.3 | 7.6 | 3.6 | 1.5 | 26.4 |
| LLM, uncached, gemini-3.5-flash-lite | 9.4 | 4.3 | 7.6 | 4.1 | 3.4 | 28.7 |

Run: 11 calls, ~136k prompt + 23k completion tokens for 4,502 messages, 64 s, no 429s.
Flash-lite is not deterministic at temperature 0: two uncached runs proposed 166 and 235 loops, and
loop points moved by about ±0.5.

## Model comparison (same 22k-token batch, 25 answer sources in it)
| model | time | loops | hits | note |
|---|---|---|---|---|
| gemini-3.5-flash-lite | 29 s | 173 | 20 | best recall, noisy |
| gemini-3.1-flash-lite | 5 s | 19 | 6 | fast, too lazy |
| gemini-3.5-flash (effort low) | 71 s | 32 | 10 | full dev run took 22 min of model time |
| gemini-3.6-flash (effort low) | 30 s | 57 | 14 | best precision, half the recall |
| gemini-3-flash-preview | 28 s | 1 | 0 | unusable here |
| gemini-3.7 / 3.8-flash | - | - | - | 503 overloaded at test time |
| gemini-2.5-flash | - | - | - | retired for new keys |

## Open issues
- Loop precision is about 10-25%. The dev key only lists loops their own system found, so part of the
  noise may be real loops that are simply unlabelled.
- Help triage is unscored on dev. It still uses the conservative rules in `add_help`.

---

# Session 2 (same day): goals, help, circles, determinism

## Asked
Raise the dev score further; make sure goals and where-to-help actually use the context even though
dev cannot score them; complete WRITEUP.md.

## Found
- Goals: the keyword miner cited "5th is a holiday" as a travel goal. An invented goal costs points.
- Help: due dates in 2025 (the model got the year wrong), so reminders fell before the data started.
  "plan" in a title triggered assist on spouse chats ("Decline Amravati plan"). Every assist step was
  the generic "Draft a reply".
- The model shortens ids ("M2793" for "M02793"). Goals and loops with such ids were silently dropped.
- An earlier shell heredoc had written literal backspace characters into a regex (`\b` became 0x08).
  I scanned both files and fixed it.
- Prompts differed between runs: circle profiles sampled messages from a Python set, so the order
  varied with the hash seed. That changed the prompt, missed the cache and changed the verdicts.

## Changes
- Circles: one batched model pass over per-person profiles. It overrules only "weak" rule guesses
  (group votes or the default), and only with sure=3. On dev: rules 0.78, model only 0.76, merged
  with sure>=2 0.78, merged weak-only with sure=3 0.80.
- Goals: one model call over a pool of Arjun's substantive lines, his wife's plan lines and samples
  from activity/trip groups, plus his group list. Evidence ids are verified and normalised. The rule
  fallback now uses only Arjun's own explicit phrases.
- Help: the model suggests action and next step; ordered guardrails decide (see WRITEUP).
  `remind_at` is in IST, never in the past; due dates are sanity-checked against the source date.
- Loops: two views (boundaries shifted by half a segment, different packing), unioned. Two
  independent runs had agreed on under a third of loops; the union gave +0.8 found+closed offline.
- Rejected: allowing loops from groups of at most 4 (6.6 vs 7.7 found+closed); marking stale
  requests done (p(done) by age is 0.59-0.78, below the 0.67 break-even except for 9 loops); linking
  colleagues tagged with a company name as `runs` (orgs 4.0 vs 4.3).
- Determinism: tie-broken sampling. Two consecutive runs now give byte-identical output, and the
  second makes zero API calls.

---

# Session 3 (same day): organisations, loops found, loops closed

## Asked
Show where the organisations / loops found / loops closed checks fail and why; then apply all
proposed fixes (approved), explain how the LLM can help further, and run diagnostics. Added CLAUDE.md
(never read solution.py whole).

## Diagnosis (scratchpad why.py against data/dev/answers)
- Scorer: loops closed counts only found loops, over all 74 answer loops, so it is capped by recall.
- Loops missed: 10 in groups (all group loops were dropped), 7 candidates the model never proposed,
  6 non-candidate short lines ("Stand fan", "12:30 pm", photos), 3 lost to merge/weight filters.
- The key repeats sources (M00391 is the source of 7 answer loops). Not exploited: emitting copies
  would game the dev key.
- Closed: 12 matched loops done in the key but open in ours, 9 of them spouse "pls pay/order" errands
  with no closing message in the key.
- Orgs: SUDAR in three companies but linked to one; "<X> operations" groups linked nobody; 1:1s with
  multi-company people tied to one company; links for team-group talkers the key does not link.

## Changes and dev deltas (cached replies, same model draw)
| change | result |
|---|---|
| baseline | 28.4 |
| group loops only when Arjun's own / reply to him / his name (`LLM_GROUP_LOOPS=addressed`) | 28.8 |
| tried: keep only loops both views agree on (`LLM_LOOP_FILTER=agree`) | 27.9 (found +0.4, closed -0.9), not used |
| spouse errand → done (`stale_errand_done`), looser regex | 29.4, 1 false close |
| same, imperative-only regex + same-topic chase check | 29.8, 0 false closes |
| `ORG_OPS` (ops-group colleagues run X) | orgs 4.3 → 4.8 |
| `ORG_MULTI` (multi-company 1:1 → person) | orgs → 4.9, chats 7.6 → 7.7 |
| `ORG_TALKERS` off | orgs +0.1 alone; with the two above 5.1 |
| `ORG_TAGGED` (name tag + membership) | orgs 4.1, left off |
| final | **30.7** |

---

# Session 4 (2026-11-07): guard against fitting dev, then improve

## Asked
Explain why `COLD_START_DEBUG` changed nothing (it only writes `llm_loops_debug.json`; all replies were
cached, 0 API calls). Then: a plan to improve the score without overfitting dev/example; plan approved.

## Evaluation added (scratchpad eval.py)
Median of several uncached draws (one draw moves the total by up to 2.0); week-2-only loop scoring
(mirrors the hidden set); seed leave-one-out for rule circles (5/10); a per-regex firing audit;
example/ as a check for goals and help, never tuned to.

## Changes
| change | result |
|---|---|
| removed one-thread phrases from rules (place name, "adhd test for your son", "outlet expansion", "kya banana", "is leaking again", ...); generic words kept | rules-only circles 9.4 → 9.1 (P73 lost); model total within noise |
| prompt examples copied verbatim from dev replaced with generic ones; company-tag hint no longer names dev companies | fresh draw 29.8 (draws before: 30.7, 31.8) |
| hard-coded `\barjun\b` → name taken from ME's saved name | no dev change; hidden set safety |
| trip groups: "<Place> <Month/Year>" instead of a place name; "<X> ops" accepted like "<X> operations" | no dev change |
| bug: goals reply as a bare list was dropped (0 goals); `llm_items` accepts both shapes in status, circles, goals | goals 0 → 1 on dev |
| help: a work decision question Arjun owes → remind (problem statement) | example help 0.8 → 1.0; dev unchanged |

## Tried and rejected
- Merging near-duplicate loops: -0.4 to +0.2 depending on draw and threshold.
- Verifier pass for precision: most false positives look like real, unlabelled tasks ("Pls make the
  above two payments"), so a verifier would cost calls for little gain. Not built.
- Dropping loops owed by others: dev key has 12/74 and example 4/10 of them; would trade recall.
- "Found nearby, different source" (25-32 misses) is mostly a different task in the same chat, not a
  wrong id: no source-snapping rule.
- Spouse commitments → done: 11/15 week 1 but 6/12 week 2, below 2/3. The existing errand rule holds
  (3/3 right in week 2 on both draws).

## Scale
Synthetic 6 weeks (13,506 messages): 162 s, 29 calls, 370k prompt + 63k completion tokens.

## Session 4, part 2: the three model-heavy changes, and the write-up trimmed
Built behind switches, each measured on 3 independent runs (own reply cache per run), 5 settings each:

| setting | run A | run B | run C | median | extra calls |
|---|---|---|---|---|---|
| none | 29.8 | 31.2 | 30.5 | 30.5 | 0 |
| `LLM_SECOND=1` second look at marked lines no view proposed (±5 lines) | 30.3 | 31.3 | 30.5 | 30.5 | +18-19 |
| `STATUS_XCHAT=1` status with on-topic lines from other chats (2 days) | 29.8 | 30.8 | 30.5 | 30.5 | +2-3 |
| `ORG_LLM=1` ventures with no group chat | 29.8 | 31.2 | 30.5 | 30.5 | +1 |
| all three | 30.3 | 30.9 | 30.5 | 30.5 | +21 |

- Second look: never worse, but no median gain, for +75% calls (cost is 12 points). Off.
- Cross-chat: 8 new closes over 3 runs, 7 unlabelled, 1 open in the key, 0 done. Off.
- Ventures: the model returned `{"ventures": []}`; the lines don't show the missed orgs. Off.
- Also: `parse_llm_json` now uses `llm_items` (accepts a bare list or another key).
- WRITEUP.md trimmed from ~2,600 to ~1,340 words (2-page limit), with the evaluation protocol and the
  measured-and-off experiments.
