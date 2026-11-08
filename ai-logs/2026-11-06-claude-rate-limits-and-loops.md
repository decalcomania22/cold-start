
## Session 5 (2026-11-08): can the score go higher? Proof of the ceilings
Added `tools/ceiling.py` (reads data/dev/answers) and a "How far can it go?" section in WRITEUP.md.
- Circles: 9 wrong, all with a 1:1 and 3+ messages. For 3, the text points to another circle (a "relative"
  saved with a company tag who says "Hey boss, got promoted"; a "relative" discussing a bot/catalog; a
  "client" who is a learning centre). 2 are sibling/cousin or parent/aunt with no cue. About 4 are reachable.
- Orgs: Farmhouse (a caretaker, photos only) and Nexus DaaS (one 1:1, venture never named) are not inferable;
  the ceiling with the other 5 perfect is 5/7 = 0.714 (5.7/8).
- Loops found: 16/74 key loops share a source, so recall ≤ 0.85 with one loop per source. The key is
  incomplete: 4 of the spouse's 11 explicit "pls book/buy/call" requests are not listed.
- Loops closed: 0 of the key's 49 done loops cite a closing message. Ours beats both blanket strategies in
  all three runs (3.8/4.5/4.2 vs all-open 3.0/3.4/3.2 vs all-done 0.0).
- Conclusion: with every reachable item fixed, about 32-33 on dev, mostly one-off cases (fitting risk).
