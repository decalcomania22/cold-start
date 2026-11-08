# AGENTS.md — Multi-Agent Engineering Blueprint

## 1. Project Context & Objectives
You are building the **cold-start intelligence engine** for Xpert, an executive WhatsApp assistant.
The engine ingests WhatsApp chat histories (~300 chats, ~20k messages in English, Hindi, Bengali, Hinglish) and generates a structured `output.json` mapping:
1. **People**: Circles (12 mutually exclusive types), links to organisations, caretaking roles (`looks_after`).
2. **Organisations & Chats**: Home vs. Work organisations, user role, and chat associations.
3. **Goals**: Up to 10 goals with direct message ID citations.
4. **Open Loops**: Commitments, follow-ups, deadlines, and questions, including closure state (`open`, `done`, `dropped`).
5. **Help Triage**: Action decisions (`assist`, `remind`, `leave`).

### Critical Scoring Guardrails (100 Points Total)
- **False "Done" Penalty**: Marking an open loop as `done` costs far more than missing a loop entirely. Default ambiguous loops to `open`.
- **False Assist on "Leave" Penalty**: An incorrect `assist` or `remind` on a private/staff `leave` loop incurs the highest penalty. Bias heavily toward `leave` for family and staff.
- **Goal Hallucination Penalty**: Every goal must cite real message IDs. Never guess or hallucinate goals.
- **Budget & Time SLA**: Maximum 30-minute runtime on the hidden test set. Minimal LLM spend ($/1,000 msgs) scores up to 12 points.

---

## 2. Agent Workforce Roster

When collaborating on this repository, adopt one of the following specialized agent roles:

```
                      ┌────────────────────────────┐
                      │   Lead Architect Agent     │
                      │  (Pipeline & Score Guard)  │
                      └─────────────┬──────────────┘
                                    │
       ┌────────────────────────────┼────────────────────────────┐
       ▼                            ▼                            ▼
┌──────────────┐             ┌──────────────┐             ┌──────────────┐
│  Graph &     │             │  Loops &     │             │  Cost & LLM  │
│  People Agt  │             │  Triage Agt  │             │  Optim Agt   │
└──────────────┘             └──────────────┘             └──────────────┘
```

### Agent 1: Lead Architect & Score Guard
- **Scope**: Pipeline orchestration in `solution.py` and `run.sh`.
- **Duties**:
  - Enforces schema conformity against `schema.json`.
  - Runs regression checks with `python check.py data/dev output.json` before and after every modification.
  - Guarantees end-to-end execution completes within 15 minutes locally.

### Agent 2: Graph & Entity Agent (`src/people_orgs.py`)
- **Scope**: Circles, organisations, and chat ties.
- **Duties**:
  - Propagates seed relationships across group chat co-occurrences.
  - Applies title and kinship regexes on `sender_name` (e.g., "Dr.", "CA", "Bhabhi", "Driver").
  - Clusters multi-participant chats into `home` vs `work` organisations.

### Agent 3: Open Loops & Triage Agent (`src/loops.py`)
- **Scope**: Loop detection, status tracking, and help triage.
- **Duties**:
  - Identifies commitments, deadlines, and unanswered questions.
  - Traces subsequent messages in the thread for resolution tokens ("done", "received", "paid").
  - Enforces conservative triage rules (`leave` vs `remind` vs `assist`).

### Agent 4: Goals Mining Agent (`src/goals.py`)
- **Scope**: Explicit personal and professional goals.
- **Duties**:
  - Filters high-intent messages sent by `ME` containing milestone or habit indicators.
  - Limits output to at most 10 structured goals backed by explicit message citations.

### Agent 5: Cost & Token Optimization Agent (`src/llm.py`)
- **Scope**: Prompt engineering, caching, and model selection.
- **Duties**:
  - Filters out conversational noise (stickers, media, short greetings) before sending prompts to the LLM.
  - Prompts economical models (`gpt-4o-mini`, `deepseek-chat`) using structured JSON outputs.

---

## 3. Modular Agent Skills (Implementation Recipes)

### Skill A: Seed Propagation & Kinship Heuristics
- Match `sender_name` against known role patterns:
  - **Staff**: `driver|cook|maid|gardener|cleaner|car wash|press|iron`
  - **Vendor**: `ca|advocate|lawyer|doctor|dr\b|plumber|electrician|carpenter|painter`
  - **Family**: `papa|mummy|maa|dad|mom|chachi|chacha|mama|mami|bhabhi|bhaiya|beta|didi`
- If person $X$ co-occurs in a work group with 3 seeded `colleague`s, classify $X$ as `colleague`.

### Skill B: Speech-Act Loop Candidate Detection
- Filter candidate messages using high-signal linguistic patterns:
  - **Commitment**: `(will|shall|i'll)\s+(send|share|transfer|call|check|do|pay)|kal\s+(bhejta|karta|deta)`
  - **Followup**: `let me know|waiting for|any update|did you get`
  - **Deadline**: `by (today|eod|tomorrow|monday|next week)|\d{1,2}(st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)`
  - **Question**: Messages ending with `?` directed to `ME`.

### Skill C: Loop State Resolution Logic
```
Has a subsequent reply occurred in the same chat within 7 days?
  ├── Contains ("done", "received", "paid", "sent", "ho gaya", "kar diya", thumbs-up emoji)
  │     └── Mark as 'done', cite closing message ID.
  ├── Contains explicit cancellation ("cancelled", "drop this", "mat karo", "rehne do")
  │     └── Mark as 'dropped', cite closing message ID.
  └── Otherwise / Ambiguous
        └── ALWAYS mark as 'open' (preserves false-done guardrail).
```

### Skill D: Assist / Remind / Leave Decision Tree
```
Is the circle in {spouse, child, parent, in-law, relative}?
  └── 'leave' (reason: "personal")
Is the loop owed by staff or already delegated?
  └── 'leave' (reason: "staff handled")
Is it a strategic decision or personal sign-off requiring Arjun?
  └── 'remind' (provide reminder timestamp)
Is it a private, reversible preparatory task (drafting a reply, researching options)?
  └── 'assist' (provide 1-line next step, state if Arjun's confirmation is needed)
```

---

## 4. Engineering Protocols & Operational Rules

1. **Verify Before Modifying**:
   Always execute `python check.py data/dev output.json` before altering any module to observe baseline scores.
2. **Never Break Schema Integrity**:
   Verify dictionary vs list types in `schema.json`. Every required key (`id`, `circle`, `links`, `looks_after`, `type`, `side`, `role`, `chat_id`, etc.) must be present.
3. **Preserve Determinism**:
   Seed knowledge takes precedence. Set temperature to `0.0` on all LLM calls.
4. **Log Changes for Submission**:
   Save session logs in `ai-logs/` detailing prompts, decisions, and accuracy deltas.
