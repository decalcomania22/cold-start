# Write-up: Cold Start

`./run.sh <input_dir> <output.json>`. Python 3.9+, standard library only. Model: **`gemini-3.5-flash-lite`**
via Gemini's OpenAI-compatible endpoint (`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`). With no key or
`COLD_START_LLM=0` it runs on rules alone and still writes a valid file.

## Focus, and why
1. **Open loops: found, closed and where to help (38 points).** This is the largest block, the weakest part of
   the starter, and the part where reading the text matters most, so most of the model budget goes here.
2. **Protecting points.** A false `done` and a wrong `assist`/`remind` on a `leave` cost points: nothing closes
   without a meaningful cited message, `leave` wins every tie, and every goal cites verified messages.
3. **Cost and reliability.** About 25 batched calls per run, with pacing, retries, a fallback model and a disk
   cache. Rules cover circles, organisations and chats, and the model is a second opinion there.
4. **Not fitting dev.** Every name in the hidden set changes. No rule or prompt may contain a dev name or a
   phrase from a dev message (see *Evaluation*).

## Approach
**Circles.** Rules read the saved name and conversation cues, then group co-membership votes. One batched
model pass reads a profile per person and overrules a guess backed only by votes or the default, but only
when it is sure (3/3). Seed circles are never overruled.

**Organisations and chats.** Seed company names become regexes (the name, its acronym, its first word).
Groups go to a company or to Home (flat numbers, "kitchen", "carpool", society words). "<X> operations/ops"
groups become a company Arjun helps run, and its colleagues run it. Staff saved as "… Office" support an Office
workspace. A 1:1 goes to the company only for an internal colleague of a single company; otherwise it goes
to the person.

**Open loops.**
- *Which chats:* only chats Arjun takes part in; a busy group is cut to ±6 messages around his involvement.
  Only the last 14 days are candidates, the window the hidden set is scored on.
- *Attention:* a regex marks likely loop lines `>>`, and the model must rule on each. The chats are read
  twice with shifted boundaries and the results unioned: two flash-lite readings agree on under a third of loops.
- *Precision:* the model rates each loop 1–3 and only 3s are kept. A group loop is kept only if it is Arjun's
  line, a reply to him, or names him. Keeping only loops both readings agree on raised *found* but cut
  *closed* by more, since *closed* is counted over all answer loops.
- *Status:* the spouse rule loops get a batched status judge. A `done` needs a cited later message, a bare
  "ok/👍" never closes, and from others the closer must say "paid/received/booked…". One exception: the
  spouse's imperative errands ("pls pay / order / book"), at least two days old, that Arjun answered and she
  never chased, are `done` (6 of 7 on dev, above the 2/3 break-even; 3/3 in week 2 on both runs I checked).

**Where to help.** The model suggests and ordered rules decide. Staff matters, family, friends and vendor-owed
loops get `leave`; spouse loops get `leave`, except his booking or research tasks (a private `assist` that needs his yes).
A work loop someone else owes gets `assist` (a drafted nudge). His own decisions, payments and meetings get `remind`
(09:00 IST on the due day, else 10:00 the next morning); anything else gets `assist`.

**Goals.** One call over Arjun's substantive lines, his wife's plan lines and samples from activity and trip
groups. Evidence ids are verified, unsure goals are dropped, and the output is capped at 8. Reply parsers
accept a bare list as well as `{"goals": [...]}`: one dev run lost its only goal to that.

## Evaluation (how I avoided fitting dev)
One uncached run moves the dev total by up to 2 points, so a change is kept only if it wins on the
**median of three independent runs**, each with its own reply cache. Further checks:
- loops are also scored on week 2 alone, the way the hidden set is scored;
- the rules' circles are tested by hiding each seed person in turn;
- `python tools/robustness.py` rebuilds dev with every person and company renamed, as the hidden set will be.
  The rules score the same on 12 renamings (26.9), and three model runs score 29.3/29.7/30.9 (dev 29.8–31.2).
  It found two name-dependent rules, both now fixed: a company name matched inside a longer word, and a
  company's first word had to be 5+ letters;
- `python tools/make_synth.py` writes a new 4-week world (another founder, 49 chats, every circle, org type,
  role, goal area/type/horizon, loop type/status and help call) with my own key. `./run.sh data/synth out.json`
  scores 41.7/43.2/43.2 of 74 there (goals 0.67, loops found 0.75, help 0.2). It exposed four general gaps, now
  fixed: "K&C" for a seed company "Kettle & Crumb", "Residents"/"B-Wing" groups as Home, a delivered file as a
  closer, and his own family bookings as `assist`. Help stays low because group loops are filtered; relaxing
  that filter lost points on real dev data in all four replays I tried, so it stays;
- goals and help are checked on the labelled `example/` set (66.5/74), which is never tuned to.

I removed all one-thread phrases, such as a place name, "adhd test for your son" and "kya banana", and all prompt examples copied from dev. That cost 0.3 on rules-only circles and nothing measurable with the model.
Built, measured over three runs, then removed (each scored a median of 30.5, the same as without it):
- a second look at marked lines neither reading proposed: +18–19 calls (+75%), and cost is scored;
- status judged with on-topic lines from other chats: of 8 new closes, 7 aren't in the key, 1 is open there and none is done;
- a call to find ventures with no group chat: the model found none, because the lines don't show them.

Rejected without building: merging near-duplicate loops (the effect changed sign between runs), a verifier
pass (most "false" loops are real tasks the key doesn't list), dropping loops others owe (12 of 74 in the key),
and marking spouse commitments `done` (73% done in week 1 but 50% in week 2).

## Scores on dev (`python check.py data/dev output.json`)
| | Circles /12 | Orgs /8 | Chats /8 | Found /14 | Closed /14 | Total /56 |
|---|---|---|---|---|---|---|
| Starter rules | 9.4 | 3.1 | 7.6 | 3.6 | 1.5 | 25.2 |
| Mine, rules only | 9.1 | 5.1 | 7.7 | 3.6 | 1.5 | 26.9 |
| Mine with the model (3 independent runs; median) | 9.4 | 5.1 | 7.7 | 3.9–4.5 (4.2) | 3.8–4.5 (4.2) | 29.8–31.2 (**30.5**) |

## How far can it go? (proof: `python tools/ceiling.py output.json`)
The dev score is near what the data supports. What's left is mostly information the chats don't contain, gaps
in the key, or run-to-run noise (±1 point). Per part:

| Part | Now | Reachable | Why not more |
|---|---|---|---|
| Circles | 9.4 | ≈10.5 | All 9 wrong people have a 1:1 and 3+ messages, but for 3 the text points to a different circle than the key (which reflects what Arjun knows): a "relative" saved with a company tag who says "Hey boss, got promoted", a "relative" who only discusses a bot and a catalog, and a "client" who is a learning centre selling a test for his son. Two more are family subtypes (sibling vs cousin, parent vs aunt) with nothing in the chat to tell them apart. About 4 are reachable. |
| Orgs | 5.1 | ≤5.7 | Two of 7 key orgs can't be found from the text: "Farmhouse" is one caretaker who sends only photos, and "Nexus DaaS" is one 1:1 whose venture is never named. Even with the other 5 matched perfectly the score is 5/7 = 0.714. A model call shown those chats found nothing. |
| Chats | 7.7 | ≈7.8 | 3 misses: one 1:1 belongs to the invisible venture above. |
| Loops found | 4.2 | unknown | 16 of 74 key loops share a source message, so one loop per source can match at most 63 (recall ≤ 0.85). Precision can't be measured cleanly because the key is incomplete: 4 of the spouse's 11 explicit "pls book/buy/call" requests are not in it ("Pls book my hyd ticket"). |
| Loops closed | 4.2 | ≤ recall × 14 | **None of the key's 49 done loops cites a closing message**: "done" reflects what Arjun knows, not what the chat shows. Our statuses beat both blanket guesses in every run (ours 3.8/4.5/4.2; all open 3.0/3.4/3.2; all done 0.0). More "done" guesses only pay off above 2/3, which no general rule reached in week 2. |

Even with every reachable item fixed, the dev total would be about 32–33, and most of that gain would come
from one-off cases. Chasing them would fit dev rather than the hidden set.

## Cost
Dev (4,502 messages): about 25 calls, 280k prompt and 65–95k completion tokens, about $0.06 per run or $0.013
per 1,000 messages (assuming $0.10/M input and $0.40/M output). A synthetic 6-week set (dev three times, 13.5k messages) took 162 s and 29 calls,
about $0.005 per 1,000 messages: loops read only the last 14 days, and circle profiles grow with people, not
messages. Rate limits are handled by pacing (`LLM_RPM`), `Retry-After`, a fallback model and a
circuit breaker, and the 30-minute limit is far away. Model: on a 22k-token batch with 25 known loops, flash-lite
caught 20, 3.6-flash 14 and 3.5-flash 10 (too slow).

## Where it's wrong (expected on the hidden set)
- **Loops found: F1 about 0.25–0.35.** Precision is about 20–25% against the dev key, though most "false"
  loops look like real tasks. Misses: short contextual lines ("12:30 pm", a photo), loops inside big groups,
  and a task that is spotted but cited on a different message than the key's.
- **Loops closed: 0.3–0.4, capped by recall.** I under-call `done` when a loop closes off the chat (a call, a
  meeting, a bank transfer). Expect 1–3 false dones per run, where Arjun's reply looked like delivery.
- **Where to help: biased to `leave`.** I expect `leave` to be right over 80% of the time and `assist`/`remind`
  50–60%. Likely mistakes: `remind`/`assist` swaps on his work loops, and leaving spouse errands he wanted help
  with.
- **Circles: about 75–80%.** Client vs colleague in 1:1 work chats, family subtypes (sibling, relative or
  in-law), and silent members of big groups, who default to colleague. Renamed people hurt the name rules more
  than the model.
- **Organisations and chats: orgs about 0.6, chats about 0.95.** Small colleagues (1–6 messages) go unlinked,
  and ventures that show up in only one 1:1 are hard to find.
- **Goals: precision above 60%, recall about 30%.** Habits and trips that show only through membership in a
  group are missed. On the example set: 2 of 3 found, none invented.
