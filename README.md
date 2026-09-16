# MULCA — Multi-User LLM-based Conversational Agent

A Discord bot instantiable with different personas/strategies/tasks to
mediate a multi-user conversation. Currently: a text-based prototype (with a
voice/audio extension in progress) built on Django, using two LLMs — a
lightweight intervention agent that judges *when* and *why* to speak, and a
main LLM that decides *what* to say and *how* to say it.

conda activate main
python manage.py run_discord_bot

## Architecture at a glance

**Two LLMs, four concerns.** The intervention agent owns **when** (is a
response warranted right now) and **why** (which strategy applies, and the
rationale) — it's a lighter, faster model built for judgment calls, watching
the conversation continuously. The main LLM owns **what** gets said and
**how** — the actual phrasing, tone, and delivery. The intervention agent's
output is handed to the main LLM as high-level guidance to interpret (a
rationale and rough target), not a script to execute verbatim — the main LLM
is the more capable model, so it gets the room to decide execution details
itself. There's also a plain-code, non-LLM fast path for a small number of
deterministic cases (e.g. `@mainllm` as a debug bypass) that skips the
intervention agent's judgment entirely when no judgment is actually needed.

**CoALA-inspired long-term memory, four types**: **Knowledge** (semantic) —
task instructions, loaded once at boot. **Experience** (episodic) — what
happened, when, and why, persisted as an append-only audit trail
(`EpisodicLog`), separate from anything either LLM holds in its own working
context. **Skills** (procedural) — the fixed, config-defined strategy set,
plus the underlying foundation models' own general competence. **Identity** —
a persona per LLM role, loaded once at boot, plus a running
participant-roles summary that goes beyond simple identity into who's who in
the conversation.

**Working memory (WM), shared but role-scoped.** Both LLMs read from the
*same* WM object per conversation — one object, not two synced copies — but
each only sees its own namespaced slice of it (`intervention_view()` /
`main_view()`), so persona, task instructions, and internal bookkeeping never
leak across roles even though there's a single source of truth underneath.
Static fields (persona, task) are set once at boot; per-turn fields (history,
computed trigger variables, the current directive) are rewritten every cycle
by the orchestrator — the deterministic, non-LLM code that moves data between
everything and decides nothing on its own.

**Flow between the two LLMs, one cycle**: an incoming message updates shared
history and trigger variables (deterministic, no LLM call) → the intervention
agent judges whether to act → if so, its rationale is written into the main
LLM's WM slice (by the orchestrator, which only relays it, never edits it) →
the main LLM is invoked with its full context freshly assembled from WM →
its reply is dispatched back and also appended to shared history, so both
LLMs see it going forward.

**Management cycle**: every 8th message, the running conversation gets
condensed by the main LLM into a dense summary (written for another LLM to
read, not a human) plus a short raw tail, replacing the older raw history —
this keeps context bounded rather than growing unboundedly as a session
continues, and is a separate, deliberately less-frequent process from the
per-message judgment cycle above.

**How each LLM actually gets its prompt, mechanically**: the intervention
agent is a *persistent* session — persona, task, and the strategy catalog are
sent once, at connect time, and it accumulates its own memory of the
conversation from there, only being shown new messages incrementally after
that. The main LLM is *stateless* — every single call gets its entire context
(persona, task, running summary, recent history, the current directive)
freshly reassembled by the orchestrator from WM; nothing persists inside the
main LLM itself between calls.

See `BLUEPRINT.md` for the reasoning and tradeoffs behind each of the above.

This repo has three other documents, each answering a different question:

- **[`BLUEPRINT.md`](BLUEPRINT.md)** — the architecture and why it's built
  this way: component responsibilities, design decisions and the tradeoffs
  behind them, and open conflicts still being worked out.
- **[`prototype/README.md`](prototype/README.md)** — what's actually
  implemented right now, and how to run it.
- **[`prototype/CONTRIBUTING.md`](prototype/CONTRIBUTING.md)** — how to add new components: new conversational strategies & trigger variables, persona's, task descriptions.

Start with `BLUEPRINT.md` for *why*, `prototype/README.md` for *what's done*,
`prototype/CONTRIBUTING.md` for *how to add to it*.
