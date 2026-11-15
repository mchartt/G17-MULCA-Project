# MULCA Architecture Blueprint

A generic architecture for a Multi-User LLM-based Conversational Agent, to use with different team roles/conversational strategies/tasks. Initial deployment: maintain a non-offensive Discord group chat in a text channel, audio to follow.

This document is the architecture; `prototype/` is the first working implementation
of it.


---



## 1. Conceptual model

Four questions — *when*, *whom*, *what*, *how* — split across two LLMs:

- **Intervention LLM** (lightweight, low-latency): decides *when*, *to whom* and *how* to talk.
  Input: conversation history + precomputed trigger variables + predefined conversational strategies. Output: either
  `None`, or a **selected strategy id** + a **parameterized prompt fragment** for
  the main LLM, plus two independent boolean flags, **`needs_history`** and
  **`needs_web_search`** — orthogonal to which strategy fired (§12): are tools necessary (e.g. does
  answering well require looking something up, and from which source). Only
  `needs_history` is currently acted on to retrieve chat logs from database into working memory; `needs_web_search` is captured but
  not implemented — see §12 for exactly what does and doesn't exist yet.
- **Main LLM**: generates the utterance (*what*), using the intervention
  LLM's output as part of its own working memory. **Stateless** — every call
  gets its full context (persona, task, history, directive) freshly assembled
  by the orchestrator from WM; nothing persists in the main LLM itself between
  calls.

**Persona/task loading is symmetric and independent for both LLMs, not
routed through one another.** Each has its own persona config file, and both
read the same active task file; both are loaded once at boot, directly by the
orchestrator's config loader, into their own WM section (§3's table). The
intervention LLM does not send the main LLM its persona or task info — the
*only* thing the intervention LLM contributes to the main LLM's WM section,
per turn, is the directive itself (`strategy_id` + `prompt_fragment`), or
nothing at all if the forced-bypass path fired instead (in which case the
orchestrator writes `forced_context` directly, no intervention LLM call
involved that turn).

**Strategies are a fixed, config-defined set** (YAML), each with a trigger
condition (+ the variables it needs) and a prompt template. The intervention LLM
*selects and parameterizes* from this set — it does not compose new strategies at
runtime.

**Selection mechanism:** all
strategy files live in (`config/strategies/*.yaml`) — per instantiation the user selects which ones are active. there
is no folder-per-task or other automatic coupling between which task is active
and which strategies apply. An explicit, independent list of active strategy
ids is chosen at startup. A strategy id that isn't in the pool fails loudly at load
time rather than silently loading an empty set. Each strategy may also declare
an optional `trigger_threshold` (e.g. `{variable: gini_index, min: 0.3}`),
surfaced to the intervention LLM as a concrete number to reason against rather
than vague language ("high imbalance") — the firing decision is still the
LLM's judgment call, this just gives it something precise. A strategy may also
declare `trigger_variables: []`, meaning it has no computed signal at all and
must be judged purely from reading the conversation content directly (e.g. "is
this message hostile," "has the topic drifted") — as opposed to
variable-driven strategies like the Gini-index-based one below.




**Forced-intervention bypass ** Sometimes a second, faster runtime path is necessary. "Forced intervention" goes straight to the main LLM's
dynamic memory *without* going through the intervention LLM at all. This is a
deliberate escape hatch for triggers that shouldn't be subject to the intervention
LLM's judgment call — e.g. a moderator command or
a hard safety rule. The orchestrator detects these with plain code (not an LLM
call, same spirit as trigger-variable computation) and writes directly into the
main LLM's WM, skipping strategy selection entirely. See §2 and §3 for where this
sits in the write-ownership contract.

Note: The original forced intervention rule was a Discord `@mention` (exact string match, no ambiguity). **This was
removed**: once the intervention agent also had to judge `needs_history`
(§12), a bypass that skips the intervention agent entirely also skips that
judgment. The latency cost of always asking it was confirmed
acceptable in testing. `forced_intervention.py` now defines one rule instead:
literal `@mainllm` text, a deliberate debug/testing bypass to verify the main
LLM/dispatch path independent of intervention-agent judgment — not a
production behavior.

Two related cases remain deliberately judged, not forced, for the original
reason: a strategy (`respond_when_addressed`) handles someone naming the bot
in plain text, or a short follow-up that plausibly responds to the bot's own
last message with no name at all (e.g. "could you check that?") — recognizing
either requires reading context, not string-matching. Likewise, "someone is
being offensive/hostile" is a strategy (`non_offensive`), not a forced rule,
for the same reason. The general principle still holds: forced rules stay
narrow and literal; anything requiring interpretation — now including "does
this need retrieval" — is the intervention LLM's job.

---

## 2. The orchestrator

Deterministic, non-LLM glue code (Django-hosted). Per incoming event, it:

1. Receives a normalized `ConversationEvent` from a channel adapter (text now, audio
   later — see §6).
2. Appends it to shared conversation history in WM.
3. Recomputes trigger variables (plain code/stats — implemented: Gini index over
   per-speaker turn counts, `participant_message_counts`/`participant_shares`
   keyed by display name, `message_count`; a known-participants roster lookup
   seeds anyone present-but-silent at a count of 0, so a quiet participant is
   visible before their first message, not only after — partially resolves
   §7.6's roster question, see §4's update). No LLM call in this step.
4. Checks the event against **forced-intervention rules** (plain code — in the
   prototype, only literal `@mainllm` text, a debug/testing bypass, not a
   production rule; see §1's forced/judged split for why the rule set stays
   this narrow, and why real `@mention` was removed from here). If one matches, skip straight to step 6,
   writing the forced context into `main.forced_context` instead of
   `main.latest_strategy_id`/`prompt_fragment`.
5. Otherwise, invokes the intervention LLM (§10.1: a persistent per-scope
   session — one shared session for the group's channels, one per DM, see the
   "Channel/instance scoping" section — not a one-shot call; see §5 for the
   invocation policy). If it
   selects a strategy that's still in cooldown, the orchestrator **vetoes it
   here, deterministically** (§10.5) — downgrades to "no action" regardless of
   what the LLM picked. Otherwise writes the strategy id + prompt fragment into
   the main LLM's WM section, and records the firing for future cooldown checks.
6. Calls the main LLM, dispatches its output back to the channel adapter as it
   streams. **The bot's own reply is then appended to shared history too** so the bot doesn't keep acting because it does not realise it already acted.
7. Writes an episodic log record regardless of outcome (§4.2), including the "no
   intervention" case — needed to evaluate false negatives later, not just fired
   strategies. The log records which path fired: intervention-LLM-selected,
   forced, or none.

**Ownership contract (why direct dual-WM writes don't collide):** the orchestrator
is the *only* writer of raw/derived fields (history, trigger variables, persona,
task instructions, forced-context). The intervention LLM's output owns exactly two
fields — `strategy_id` and `prompt_fragment` — and the orchestrator's role there is
purely to *relay* that output into the main LLM's WM verbatim, never to author or
edit its content. No field has two authors; the orchestrator writing intervention
output is bookkeeping, not composition. This is stated explicitly because it was
called out as a risk to watch for — see §3 for the field-by-field table.

`main.forced_context` and `main.latest_strategy_id`/`prompt_fragment` are mutually
exclusive per cycle by construction (step 4 above short-circuits step 5), so they
never race either — the main LLM's prompt-builder reads whichever one is populated
this cycle, never both.

---

## 3. Working memory (WM)

**Decision: one shared WM object with role-scoped read/write access**, not two
separate WM objects kept in sync.

*Tradeoff considered:* two separate WMs (intervention-LLM WM, main-LLM WM) would
give a cleaner "each LLM only sees its own state" story, but require an explicit
sync step every time the orchestrator or intervention LLM's output needs to move
data from one to the other — and sync bugs (stale copies, partial writes) are
exactly the inconsistency risk the brief already worries about. A single shared
object with namespaced sections sidesteps sync entirely: there's one source of
truth, and "role-scoped access" is enforced by convention/accessor methods (each
LLM's prompt-builder reads only its own namespace), not by physical separation.
For a prototype this size, one object is simpler to reason about and to log.

**Structure:**

| Section | Set at | Owner | Written by |
|---|---|---|---|
| `intervention.persona` | boot | static | config loader |
| `intervention.task_knowledge` | boot | static | config loader |
| `main.persona` | boot | static | config loader |
| `main.task_knowledge` | boot | static | config loader |
| `main.tools_description` | boot | static | config loader |
| `shared.history` | per-turn | orchestrator | orchestrator |
| `shared.trigger_variables` | per-turn | orchestrator | orchestrator |
| `main.latest_strategy_id` | per-turn | intervention LLM output | orchestrator (relay only) |
| `main.latest_prompt_fragment` | per-turn | intervention LLM output | orchestrator (relay only) |
| `main.forced_context` | per-turn (rare) | orchestrator | orchestrator |
| `shared.recent_actions` | per-turn | orchestrator | orchestrator |

`shared.recent_actions` (implemented, §10.5's addition): `{strategy_id:
message_count when it last actually fired}` — the hard-cooldown bookkeeping
step 5 above checks before letting a strategy fire again. Not conversational
content, agent-state bookkeeping, kept in WM anyway per §10.5's "practically,
fine to put it here."

Static sections are loaded once at boot from persona/task config and not mutated
during a session. Per-turn sections are the only ones the orchestrator rewrites
each cycle. No field is written by two independent authors.

**`main.tools_description` (diagram-sourced, not designed this session).** The
suggestion diagram places "description of available tools" on the main LLM's
static startup path, after persona. This blueprint treats it as a placeholder
static field only — no tool-calling loop, tool registry, or execution sandbox is
designed here. It exists so the seam is visible in the WM contract; a tools
subsystem is future scope.

---

## 4. Long-term memory (CoALA + 4th type + 2nd LLM)

Each CoALA type now has an explicit project-level name, adopted purely for
conceptual mapping — none of these renames changed any code; they're the
existing artifacts, named:

| CoALA type | Project name | Prototype treatment | Reasoning |
|---|---|---|---|
| Knowledge (semantic) | **`knowledge_memory`** | `task_knowledge` — collapsed into WM at boot from `config/tasks/*.yaml`, one static string, no persistence/retrieval layer. | Task facts are small and static per instance. **Web search as a second source feeding this is a real todo, not rejected** — considered and deliberately deferred (would mean turning this from one static string into a structured, extensible collection), not scoped now. |
| Experience (episodic) | **`experience_memory`** | **Persisted** — `EpisodicLog` via Django ORM (§4.2), accessed through `bot/experience_memory.py` (a thin wrapper: `log()`/`recall_recent()`, not a renamed model — renaming `EpisodicLog` itself would need a migration for no functional gain). | This is the audit trail for evaluating agent behavior — needed even in v0, not deferrable. |
| Skills (procedural) | **`skills_memory`** | Explicit: `StrategyStore`, the strategy YAML pool, loaded at boot, static for the session (class name unchanged — no functional benefit to renaming it). Implicit: foundation model competence — not implemented, not modeled. | Matches the brief's own framing; nothing to add. |
| Identity | **`identity_memory`** | Persona config (`intervention.persona`/`main.persona`, static, boot-time) **plus** `participant_roles_summary` (§11 — a brief per-participant role summary, produced every management cycle alongside `history_summary`). | Identity = who the LLM is + who it understands others to be, together — distinguished from Knowledge as **who** vs. **what's known about the task/world**. Persona/task stay separate config files specifically so they're swappable independently (the reuse axis, §9). |

**Identity vs. "team role".** Confirmed scope: the brief per-
participant summary the management cycle already produces
(`participant_roles_summary`) **is** the intended "team role" semantics. One accepted limitation carried over from the
presence roster: two participants sharing an identical display name would be
conflated, since labels are keyed by display name, not stable id, for
readability.

**Presence roster** (`{user_id: display_name}`, fetched from the Discord
channel's member list) is a separate, narrower mechanism from
`identity_memory` above — it exists only for (a) recognizing a
present-but-silent participant for trigger variables (§2 step 3), and (b)
resolving human-readable names wherever a speaker is shown to an LLM or
dispatched text (`ConversationEvent.label()`, §6). It doesn't know *roles*,
only *presence* — that's what `participant_roles_summary` adds on top.

### 4.2 Episodic log schema (implemented)

One row per orchestrator cycle (`bot/models.py::EpisodicLog`):

```
timestamp, channel_id,
incoming_event_speaker, incoming_event_content,
trigger_variables_snapshot (JSON),
intervention_path ("none" | "forced" | "strategy"),
strategy_id (nullable), prompt_fragment (nullable),
main_llm_output (nullable),
```

Logged even when `intervention_path == "none"`, so "the agent chose not to speak"
is auditable too.

## Channel/instance scoping

`Orchestrator` keys `WorkingMemory`/queue/intervention-agent by **scope**
(`"group"`, or `"dm:<user_id>"` — `Orchestrator._scope_key`), not by raw
Discord `channel_id`. §2, §5, and §6 below have been swept to match; remaining
mentions of "per-channel" elsewhere in this document are describing the
*original*, now-replaced model historically, not current behavior.

**Decided channel model for one MULCA instance**: it registers to exactly
**one text channel and one voice channel** (a fixed pair, configured at
startup), and is additionally **open to receiving DMs** from any individual
user. Separate groups get separate instances entirely (confirmed: 10 groups,
10 Discord servers, one instance each) — an instance never needs to keep
multiple *independent* group-contexts apart from each other.

- **The one text channel + one voice channel share a single WM**, single
  intervention-agent session, single queue for the whole instance — genuinely
  one conversation, not per-channel state. This also fixes something the old
  per-channel model silently broke: §10.1's "one intervention agent aware of
  both text and audio streams" only actually holds if text and voice share one
  session, which per-channel keying didn't give it.
- **Each DM-ing user gets their own separate, private WM**, kept apart from
  the group's shared WM (implemented: `Orchestrator._handle_conversation_event`
  returns before the episodic-log write for any scope other than `"group"`).
  **DM content is not written to the persisted episodic log** (§4.2) the way
  group-channel content is — that's private information belonging to the
  individual user. The `EpisodicLog` schema itself still has no
  access-control concept — the exclusion is enforced entirely by the
  orchestrator never calling `log_fn` for a DM scope, not by anything in the
  model/table. Roster lookup is also skipped for DM scope (a roster has no
  meaning for a 1:1 conversation).

`channel_id` doesn't disappear in either case — it stays on every event as
**dispatch-routing metadata** (which physical channel/DM a reply goes back
to; also now doubles as the signal for "is this a DM, route to the private WM
and skip episodic persistence"). Still genuinely open, not urgent until audio
exists: for the shared text+voice pair, does a reply always go back to the
*same* channel the triggering message came from, or does modality-based
routing (text in → text out, audio in → audio out, regardless of which
triggered it) matter later? Flagged, not decided.

---

## Technical constraints 

- Discord bot, hosted on a Django server, listening to both the audio stream and
  the text channel (text built now, audio interface-only — §6).
- **OpenAI streaming models** for generation — both LLMs stream tokens rather than
  waiting for a complete response; the main LLM's dispatch to the channel adapter
  (§2 step 6) should forward partial output as it streams, not buffer the full
  completion first, so latency-sensitive turn-taking (§5) isn't made worse by
  waiting on a full generation.
- The audio path must use a **native multimodal audio-understanding model**, not a
  speech-to-text → LLM → text-to-speech pipeline. This constrains
  `AudioChannelAdapter` (§6): it wraps a model that understands audio directly, and
  whatever it hands the orchestrator as `ConversationEvent.content` is a
  representation *derived from* that native understanding, not a transcript
  produced by a separate STT stage. This is the colleague's implementation detail,
  but the constraint is recorded here since it affects what `content` is allowed to
  be.
- Code must be **documented and modular enough for students to extend** — e.g. add
  a new persona, strategy, or task config without touching orchestrator/WM/LLM
  code. This is why personas, strategies, and task knowledge are config files
  (§1, §4) rather than inlined logic, and why the WM ownership contract (§2, §3)
  is written down explicitly rather than left as implicit convention: a student
  extending this later needs the contract on paper, not just working code to
  reverse-engineer.

---


## 5. Concurrency / timing model (prototype)

**Decision: fully serialized, per scope** (implemented — see "Channel/instance
scoping" above: `"group"` for the instance's registered channels,
`"dm:<user_id>"` per DM). One `asyncio` consumer loop per scope processes
events strictly in order:

- The intervention LLM is invoked **synchronously on every incoming text message**
  (not on a timer, not on a variable-change threshold). Simplest policy that's
  correct by construction — no missed triggers, no debouncing logic to get wrong.
- If a new message arrives while the main LLM is still generating a response to a
  prior trigger, it is **queued**, not interleaved — the orchestrator finishes the
  current cycle (intervention decision → main LLM generation → dispatch → log)
  before starting the next.

**Explicitly flagged simplification:** this means the agent's read of "current
state" can lag behind the live conversation by up to one main-LLM generation
latency, and message-rate-based trigger variables (e.g. Gini index) computed on
dequeue may already be stale by the time the response posts. Acceptable for a
prototype; the fix (recompute trigger variables at send-time and allow the
orchestrator to abort/refresh a stale in-flight generation) is a known follow-up,
not built now.

Per-message invocation of the (lightweight) intervention LLM is a deliberate
prototype choice over threshold-based invocation — it's simpler to implement and
reason about, at the cost of more intervention-LLM calls than strictly necessary.
Variable-change-threshold invocation is the natural next optimization once real
trigger-variable volatility is observed.

---

## 6. Audio interface seam (TODO)

The orchestrator never talks to Discord directly. It consumes `ConversationEvent`
objects from a **channel adapter**, and dispatches replies through the same
adapter. This is the seam:

```python
@dataclass
class ConversationEvent:
    speaker_id: str        # stable platform id -- identity/matching (e.g. @mention check), never shown to an LLM
    modality: Literal["text", "audio"]
    content: str          # transcript / text content — always populated
    raw_ref: Any | None   # modality-specific payload (e.g. audio segment ref), optional
    timestamp: float
    speaker_display_name: str | None = None  # implemented, added after the original draft
    # .label() -> speaker_display_name or speaker_id: the one thing every LLM-facing
    # render and every dispatched-to-Discord string should call, never speaker_id directly
```

`speaker_display_name`/`.label()` added once it became clear that showing raw platform IDs to an LLM (and
in turn to users, in dispatched replies) was actively unhelpful. `AudioChannelAdapter`
should populate it the same way (whatever display name is available for the
speaking participant), for the same reason.

- `TextChannelAdapter` (built in the prototype): Discord message → `ConversationEvent(modality="text", content=message.content, ...)`.
- `AudioChannelAdapter` (TODO): must consume
  the native multimodal audio-understanding model's output and emit the same
  `ConversationEvent` shape — `content` populated with whatever text
  representation the orchestrator/LLMs need (e.g. a transcript, or a semantic
  summary), `raw_ref` free to carry anything audio-specific the adapter itself
  needs but the orchestrator never inspects `raw_ref`.
- Both adapters push events onto the **same per-scope queue** the orchestrator
  consumes (the group's shared queue, per "Channel/instance scoping" above,
  since the voice channel is part of the same scope as text) — the
  orchestrator's serialization model (§5) applies uniformly across modalities
  once both are live; interleaving audio and text events safely is the audio
  adapter's problem to hand events over correctly-timestamped, not the
  orchestrator's.
- Explicitly out of scope here: turn-taking detection, VAD, streaming transcript
  assembly, or how the audio model decides an utterance boundary — all internal to
  `AudioChannelAdapter`.

**Continuous event channel, in addition to discrete turns ** The
suggestion diagram's purple "Continuous Dispatching" block sends high-frequency
signals — every 200ms or on-event — separate from the discrete "End of turn
Dispatching" this blueprint's orchestrator loop otherwise runs on: raw audio,
and per-user started/stopped-speaking events, feeding *both* LLMs' trigger-variable
computation in near-real time rather than only at utterance boundaries. This is a
second, higher-frequency event lane the audio adapter owns, distinct from the
`ConversationEvent`-per-utterance model above:

```python
@dataclass
class SpeechActivityEvent:
    speaker_id: str
    kind: Literal["started_speaking", "stopped_speaking"]
    timestamp: float
```

`AudioChannelAdapter` pushes these onto a separate high-frequency channel the
orchestrator's trigger-variable computation (§2 step 3) can consume without
going through the full per-turn cycle — e.g. to keep a live "who's currently
speaking" variable current between utterances. It does **not** by itself invoke
the intervention or main LLM; only a completed `ConversationEvent` (or a forced-
intervention rule match) does that. This keeps §5's serialization model intact —
the continuous lane updates state, the discrete lane drives LLM calls — while
still giving trigger variables sub-utterance freshness once audio is live. Not
implemented in the text-only prototype; documented here as the seam's second half
alongside `ConversationEvent`.

See `prototype/README.md` for the concrete interface file and where to plug in.

---

## 7. Open questions / risks 

1. **Trigger-variable staleness under load** (§5) — compounds if the group is
   fast-moving; may need per-message vs. per-cycle variable versioning.
2. **Strategy prompt-fragment trust boundary** — the intervention LLM's free-text
   `prompt_fragment` goes straight into the main LLM's prompt with no validation.
   A malformed or adversarial-in-spirit fragment (e.g. from a jailbroken
   intervention LLM call) could steer the main LLM off-persona. Prototype accepts
   this risk; a schema/length/keyword check on `prompt_fragment` before relay is a
   cheap future guard.
2b. **Episodic log growth vs. WM history growth**
   The management cycle (§11) truncates `wm.history` to a short raw tail
   (last 5 events) plus a running condensed summary every 8th message, so it
   no longer grows unboundedly — see §11 for the mechanism. Still genuinely
   open: `EpisodicLog` itself (the persisted table) has no trimming/retention
   policy and grows forever; that's a separate, not-yet-designed concern
   (noted in `prototype/README.md`'s queue of not-yet-implemented items).
3. **Multi-channel / multi-guild identity — resolved and implemented.** Group
   channels share one WM per instance; DMs get their own, non-persisted,
   per-user WM. See "Channel/instance scoping" further below for the actual
   mechanism (`Orchestrator._scope_key`).
4. **Cost/latency accounting** — every message triggers an intervention LLM call
   (§5); no discussion yet of what happens if that call itself is slow relative to
   Discord's typing-indicator expectations. Not blocking for the prototype, worth
   measuring once real strategies are in place.
5. **Strategy config validation** — nothing in the prototype validates a strategy
   YAML file against a schema at load time; a malformed strategy file fails at
   first use, not at boot. Cheap to add (e.g. `pydantic` model for the strategy
   schema) before the reusable-strategy-database goal is worth pursuing.
6. **Per-user "team role" roster — resolved (implemented).** A *presence*
   roster (`{user_id: display_name}`) plus `participant_roles_summary`
   (updated every management cycle, §11) together are the intended scope —
   see §4's `identity_memory` mapping. No separate relational/rapport
   tracking is planned beyond this.
7. **Forced-intervention rule authorship — resolved (implemented).** Rules are
   hardcoded plain code in `core/forced_intervention.py`, not config, and
   deliberately kept to exactly one case (`@mainllm`, a debug bypass — real
   `@mention` was removed, see §1's "forced vs. judged" note for why) — see
   that same note for where the line is drawn and why "someone is being
   offensive" deliberately did *not* become a forced rule either.

---

## 8. Mapping onto the CoALA reference

The orchestrator is the non-LLM runtime substrate that hosts the decision procedure's
execution loop (event intake, trigger-variable computation, WM reads/writes,
dispatch) — CoALA doesn't name that substrate separately because its reference
agents assume a single control loop; MULCA's two-LLM split makes the substrate
visible as its own component. Concretely:

| CoALA concept | MULCA component |
|---|---|
| Decision procedure | Intervention LLM (the judgment call of *whether/how* to act) |
| (implicit control loop / runtime) | Orchestrator (deterministic host of the loop above) |
| Procedural memory | `skills_memory` — Main LLM (foundation model competence) + `StrategyStore` (§1, §4) |
| Semantic memory | `knowledge_memory` — `*.task_knowledge` (§3/§4) — "core instructions" |
| Episodic memory | `experience_memory` — `EpisodicLog` via `bot/experience_memory.py` (§4.2) — "chat logs" / decision audit trail |
| Working memory | The shared WM object (§3) — "context" + "current state (variables)" |
| Experience memory (persona/team role) | `identity_memory` — `*.persona` (§4) + `participant_roles_summary` (§4, §11, implemented) |
| Actions / Observations | Main LLM output → channel adapter (action); `ConversationEvent` / `SpeechActivityEvent` from channel adapter → orchestrator (observation) |

This mapping is documentation, not a design change — every component on the right
already exists in §1–§6 above under MULCA-specific names. It's included because it
clarifies a subtlety: the *main* LLM, despite doing the visible talking, is
procedural memory in this framing — the actual decision-making locus is the
lightweight intervention LLM.

---

## 9. Reuse grounding: example use cases

The long-term goal is a reusable database of personas, strategies, and task
configs, so a new MULCA instance is assembled rather than rewritten. Three
examples now (one implemented, two still hypothetical), to sanity-check that
the config layers (§1 strategies, §4 persona/task knowledge) are actually
swappable independently, not just in principle:

- **General moderator (implemented, currently the default)**: task config =
  `general_moderation.yaml`, no specific structured task, just "keep this
  conversation safe and roughly equal-participation"; strategy set =
  `participation_equality`, `respond_when_addressed`, `non_offensive`;
  persona = neutral moderator. This is what the prototype actually runs today
  — the consensus-ranking example below is a config the prototype *supports*,
  not what's currently active.
- **Group consensus-ranking mediator (config exists, `keep_on_topic.yaml`,
  not currently active)**: task config = the ranking exercise and its rules;
  strategy set = `participation_equality` (shared with the general moderator)
  plus `keep_conversation_on_topic`, which only makes sense once a task
  actually defines a topic; persona = neutral, formal facilitator. Nothing
  about audio.
- **D&D dungeon master for autistic kids**: task config = campaign/scenario
  content; strategy set is entirely different (e.g. pacing turns predictably,
  avoiding overwhelming multi-party cross-talk, explicit narration of whose turn it
  is) — this is the concrete case for why strategies must be swappable as a *set*,
  not just parameterized within one fixed set; persona = in-character narrator,
  warm/predictable tone. This use case is also the one most likely to need the
  audio path (§6) live, and the continuous speaking-activity signal (§6) matters
  more here than in the text-only ranking case — a DM needs to know who's about to
  speak, not just who has spoken.

Neither example changes the orchestrator, WM contract, or LLM roles — only the
three config layers (persona, strategy set, task knowledge) change between them.
That's the concrete test of whether §1/§3/§4's config-driven design actually holds
up; if a future use case *can't* be expressed by swapping just those three things,
that's a sign the architecture has leaked a use-case-specific assumption somewhere
that should have been config instead.

---

## 10. Realtime speech extensions (decided, sequenced after text)

These decisions came out of designing the audio path before building it. They
extend, and in a couple of places correct, §1–§8 above. **Sequencing**: build and
verify the text-fed version of §10.1 first (feed text events into a stateful
intervention session instead of the stateless one-shot call already built), before
adding the raw audio relay — this isolates "does the session-based intervention
pattern work" from "does the audio pipe work."

### 10.1 The intervention agent becomes one stateful, realtime-connected agent

**Decision (revises §1/§8): the intervention agent is one persistent, stateful
connection (OpenAI Realtime API) directly wired to the input stream(s)**, not a
stateless per-message call. This was a deliberate choice to unify judgment across
text and audio into a single aware agent, made knowing the cost: a persistent
session holds its own conversational memory, which is a second representation of
"what's happened" alongside WM. We are not attempting to keep the two in sync.
Instead:

- The **session is the intervention agent's own memory**, used only for its own
  judgment.
- **WM stays authoritative for what the main LLM is handed and what gets
  persisted to the episodic log** — populated from the orchestrator's own
  observation of events, not mirrored from the session's internal state.
- Trigger-variable computation stays deterministic, orchestrator-owned code
  (unchanged from §2) — the orchestrator periodically pushes computed variables
  into the live session rather than the session deriving them itself.

**Why the intervention agent doesn't use WM's role-scoped view, unlike the main
LLM.** §3 describes both LLMs reading WM through a namespaced view method
(`intervention_view()` / `main_view()`) so persona/task/history never leak
across roles. That's still exactly true for the main LLM — `main_view()` is
real and used every call. It is **not** true for the intervention agent
anymore: `intervention_view()` exists in `working_memory.py` but is never
called by anything. This is a direct consequence of the ownership split
above, not an oversight to fix: persona/task are sent **once**, as
constructor arguments, at `connect()` time — never re-read from WM per turn,
because the session already remembers them; there's nothing for a per-turn
"view" to assemble for those fields. History/trigger variables/cooldown state
*are* read every turn, but directly off `wm`'s raw attributes
(`wm.history`, `wm.trigger_variables`, `wm.strategy_in_cooldown(...)`) rather
than through a view method — because what's needed each turn is only the
*new* increment plus current dynamic state, not a full reconstructed context
the way the stateless main LLM needs. The view-method abstraction was built
for a symmetric "both LLMs get their whole context handed to them fresh"
model; the intervention agent stopped fitting that model the moment it became
stateful, and the code (correctly) reflects that asymmetry even though the
unused method was never removed.

**Signaling path is unchanged in shape, only in mechanism**: the intervention
agent's *output* always goes to the orchestrator, never directly to the main LLM
— the orchestrator remains the sole router. What changes is that the orchestrator
no longer gets this as a return value from a one-shot call; it's an event/callback
fired by the live session (e.g. a tool/function call the model invokes) whenever
it decides to intervene. §2 steps 5–7 (relay decision into WM, invoke main LLM,
dispatch, log) are otherwise unchanged.

**Text vs. audio input, concretely**: text has no raw byte stream to relay —
Discord already delivers discrete message objects. So for text, the orchestrator
keeps mediating fully (per message, forward it into the live session as a
conversation item) exactly as §2 already describes. For audio, full per-frame
mediation would reintroduce the latency Realtime API exists to avoid, so the
orchestrator's role shifts from "process every frame" to "relay the raw stream,
and separately own the control plane" — directives and interrupts, not audio
bytes. Text stays orchestrator-mediated; audio's raw data plane is relayed
directly, its control plane (trigger variables, forced/interrupt signals,
directives) still flows through the orchestrator.

### 10.2 Self-interrupt is a queue-breaking reflex, not a decision

**Correction to §5**: not everything goes through the per-scope serialization
queue. If the bot is speaking and a `SpeechActivityEvent` shows someone else has
started talking (an ordinary turn, not an intentional interruption attempt — see
§10.4), the correct response is to stop immediately. Waiting in the normal
scope's queue behind whatever's already enqueued would defeat the point of a
reflex. This is deliberately carved out as an exception to "every event goes
through the queue": the interrupt signal is fired directly, the instant it's
detected, bypassing the normal cycle. No LLM judgment is involved — it's a plain
cancel action on the main LLM's in-flight response.

### 10.3 Multi-user voice-activity detection is done ourselves, not via Realtime API's built-in turn detection

**Decision**: OpenAI's Realtime API's own turn detection is built around one
speaker per session, and can't natively distinguish which of several Discord
participants is talking — which we need for participation-balance trigger
variables (who's talking, not just that someone is). So the orchestrator (or an
audio-adapter component) taps Discord's per-user voice-receive streams directly
and does its own lightweight VAD, plain code, no LLM call — consistent with
`SpeechActivityEvent(speaker_id, kind, timestamp)` in `core/events.py`, which was
already shaped for this. This settles what was previously an open question in §6
("does the audio adapter do its own VAD, or subscribe to the session's turn-detection
events") in favor of doing it ourselves.

### 10.4 Assertive floor-claims: turntaking policy, per strategy (not built yet)

A strategy that's specifically about reclaiming the floor from a dominant speaker
(e.g. `participation_equality` used in audio) cannot use the reflexive-yield
behavior in §10.2 — if it yields the instant it detects any overlap, the dominant
speaker just talks through its first syllable and it accomplishes nothing. This
needs a distinct, per-strategy-declared policy, still audio-only/unbuilt:

```yaml
id: participation_equality
# ...trigger_description / trigger_variables / prompt_template / cooldown_messages as before...
turntaking:
  interrupt: true              # proactively claims the floor even if someone's mid-turn
  persist_seconds: 1.0         # hold ground this long before checking who "won" the floor
  on_failure: retry_after_delay  # or: do_nothing
  retry_delay_seconds: 5.0     # only used if on_failure is retry_after_delay
```

Strategies that omit `turntaking` entirely default to reflexive-yield (§10.2) —
they never proactively claim the floor. `on_failure: retry_after_delay` means an
**actively scheduled retry**: the orchestrator sets a timer and re-attempts the
strategy when it fires, rather than passively waiting for the next unrelated
message to happen to re-trigger consideration — a fully passive lapse could mean
a long, silent wait if the conversation happens to go quiet right after a failed
attempt. True "wait for the next natural lull" detection isn't reliable/fast
enough for this prototype, so a fixed delay is the deliberately honest fallback,
not a hidden compromise. `persist_seconds`/`retry_delay_seconds` are wall-clock
by necessity (floor-claiming is a real-time physical act); see §10.5 for why the
*general* cooldown mechanism deliberately does **not** also use wall-clock time.

### 10.5 WM needs to know what it already tried, and cooldown is enforced deterministically (implemented, corrected from the original design here)

**Implemented, differs from the original sketch above**: the WM field is
`shared.recent_actions` — but it's `{strategy_id: message_count when it last
fired}`, a plain dict, not the richer `{strategy_id, timestamp, outcome,
cooldown_until}` list originally envisioned. The simpler shape turned out to
be sufficient once cooldown itself was decided to be **message-count-based,
not wall-clock**: each `Strategy` declares `cooldown_messages` (0 = none), and
`WorkingMemory.strategy_in_cooldown()` compares the current turn count against
when it last fired. This applies uniformly to text and audio, since one
utterance already produces one `ConversationEvent` just like one text message
does (§6) — "5 messages" already means "5 turns of conversation" in either
modality, no seconds↔messages conversion needed or wanted (a generic
auto-converting cooldown was considered and deliberately rejected: there's no
principled duration to convert against, and it would blur this general
anti-repetition concept together with §10.4's wall-clock floor-claim retry
timing, which is a different concept that only superficially shares the word
"cooldown").

Two uses of this field, deliberately split by which one needs a hard guarantee:

- **Hard guarantee, orchestrator-enforced**: if the intervention agent selects
  a strategy that's still in cooldown, the orchestrator **vetoes the decision
  after the fact** (downgrades to "no action"), rather than trying to hide the
  option from the model in advance by rewriting its tool schema mid-session
  (rejected as unnecessary complexity, given the persistent-session
  architecture in §10.1 — the veto achieves the same guarantee on the actual
  outcome). This is plain code, not something we rely on the model to notice
  and self-restrain from in a text note — consistent with keeping
  correctness-critical logic outside LLM judgment, same principle as
  trigger-variable computation (§2).
- **Soft context**: which strategies are currently in cooldown is also told to
  the intervention agent directly (so it doesn't waste attempts re-selecting
  something it can already see is blocked), but this is a nudge only — the
  veto above is what actually guarantees the outcome.

**Not every strategy should have a cooldown.** `respond_when_addressed` (fires
in direct response to being addressed) and `non_offensive` (a safety
intervention) both deliberately have `cooldown_messages: 0` — the former needs
to fire on consecutive back-and-forth messages, and the latter shouldn't be
suppressed just because it fired recently if the same behavior continues.
Cooldown is for unsolicited, nagging-prone interventions
(`participation_equality`, `keep_conversation_on_topic`), not a default every
strategy should get.

### 10.6 Open questions this section still leaves (not blocking text-first sequencing)

- Should there be a cooldown specifically *after a failed floor-claim* that's
  longer than the general `cooldown_messages`, so a repeatedly-rebuffed
  interruption attempt doesn't keep retrying on the same cadence and start to
  feel naggy? Not resolved — this would need its own wall-clock field
  alongside `turntaking.retry_delay_seconds` (§10.4), since it's the same kind
  of real-time concern, not the general per-turn cooldown.
- `shared.recent_actions` retention/growth is unbounded as implemented (one
  entry per strategy id, so it's small and self-limiting in practice, but
  this hasn't been stress-tested) — same spirit as §7.2b's WM-history-growth
  question.

---

## 11. Management cycle (implemented)

Addresses §7.2b's WM-history-growth question directly.

**Trigger**: every 8th (non-bot) message, not a timer — consistent with the
rest of this document's "message-count, not wall-clock" bias (§10.5) and
simple to reason about. Implemented via `WorkingMemory.total_message_count`, a
monotonic counter that (unlike `len(wm.history)`) survives the truncation
below, so "every 8th message" keeps meaning what it says even after the
history window has been compacted several times over a long session.

**Mechanism**: a **separate call/method, `MainLLM.run_management_cycle(wm)`**,
not folded into the per-turn `decide()` call — keeping the per-turn decision
path single-purpose and fast was the explicit reason for this split, not a
stylistic preference. the intervention agent is meant to be
lightweight/fast for judgment calls, not scoped for dense synthesis. Moved to
the main LLM, which is stateless (§1) and has no session memory to fall back
on, so it now **revises** the existing `history_summary`/
`participant_roles_summary` each cycle (previous summary + new raw messages
since last cycle → updated summary) rather than regenerating from an
unbounded memory it doesn't have.
**Serialization**: no new event type — implemented as a plain check inside the
existing per-message consumer loop ("is this the 8th message since the last
cycle? if so, also run the management step after the regular turn"), rather
than a dedicated queued event. This gives the identical serialization
guarantee as a separate event type would, with less plumbing — deliberately
chosen over the more "architecturally pure" separate-event-type option for
exactly that reason.

Note: `RealtimeInterventionLLM` tracks `_sent_history_count`, an absolute
index into `wm.history`, to know which items it has already pushed to its own
session for `decide()`'s judgment. Truncating `wm.history` out from under
that counter would silently break the next `decide()` call's slice math --
still true even though `RealtimeInterventionLLM` no longer produces the
summary itself, since it still needs to track what it's sent. Fixed via
`on_history_truncated(wm)`, which the orchestrator calls immediately after
`WorkingMemory.apply_management_cycle()` regardless of which model ran the
cycle — the events remaining after truncation were already sent before the
truncation happened, so this just re-points the counter at the new (shorter)
list length, not a resend.

**Scope**:
1. Update a running conversation-history summary in WM.
2. Update a summary of participants and their roles (`identity_memory`, §4 —
   the presence roster is not this; this is the actual role semantics that
   roster stops short of).
3. Room to discover more needs once built — deliberately left open rather
   than speculatively designed now.

**Scope restriction**: the management cycle applies only to the
`"group"` (channel) scope — it must never run for a `"dm:<user_id>"` WM. DM content
already can't reach the persisted episodic log (per "Channel/instance
scoping" above); it shouldn't get folded into any summary either, group-level
or otherwise. When building the every-8th-message trigger, gate it on
scope, not just message count.

**Logged (implemented)**: management cycle runs get their own episodic log
entries, `intervention_path == "management_cycle"` — no schema change; the
existing `main_llm_output`/`prompt_fragment` free-text fields hold
`history_summary`/`participant_roles_summary` respectively for this row type,
rather than adding a dedicated table.

**§7.2b's WM-history-growth question — decided, target size revised upward.**
`shared.history` gets *replaced*, not appended to alongside: a condensed
running summary (target **~1,500 characters / ~250-300 words**, a budget not a
hard rule — expressed to the model as a word-count target, not a hard
character truncation, since truncating generated text at an exact character
count risks cutting off mid-sentence) covering everything before it, plus
the last 5 `ConversationEvent`s kept in full. This is what the management
cycle produces each time it runs — the summary absorbs whatever's aging out of
the raw tail, so the window is fixed-size going forward rather than growing
unboundedly with session length.

**Two different summaries, two different prompts — not one shared
summarization prompt.** This resolves what §12 originally left open:
- The **WM/internal summary** (what the management cycle produces above) is
  written *for the LLMs to read*, not for a human — optimized for information
  density, as condensed as possible while staying usable as context.
- The **user-facing summary** (§12's `provide_summary` strategy, when someone
  directly asks "what have we talked about") is written *for the human
  asking* — optimized for readability/formatting, not density. Same
  underlying idea (summarize what happened), deliberately different prompts
  because the reader and the objective differ.

### 11.1 Startup/shutdown persistence (implemented)

Previously: "memory" only lasted one process run — a restart lost everything
in WM, leaving only the raw episodic log to reconstruct from (and nothing did
that reconstruction). **Now: WM's condensed state is written to long-term
storage on shutdown, loaded back on startup**, keyed by instance identity —
concretely, `WorkingMemorySnapshot.channel_id`, resolved once at boot as the
first (sorted) entry in `MULCA_CHANNEL_IDS` (`persistence_channel_id` in
`run_discord_bot.py`). If `MULCA_CHANNEL_IDS` is unset, there's no single
stable identity to key by, so persistence is silently disabled rather than
guessing — not by DM, ever, since DM state is never persisted at all
(BLUEPRINT.md's "Channel/instance scoping" section).

- **On shutdown**: `Orchestrator.save_group_snapshot()`, called from
  `run_discord_bot.py` right after `client.run()` returns. `discord.py`
  handles `SIGINT`/`Ctrl+C` internally and returns from `client.run()`
  normally rather than raising, which is what makes this work without a
  custom signal handler. Persists the running summary + last-5-messages tail
  (§11's WM shape) + `total_message_count`, as one row, into
  `WorkingMemorySnapshot`.
- **On startup**: `Orchestrator.load_group_snapshot()`, called from
  `discord_adapter.py`'s `on_ready` before any message can arrive — seeds
  `shared.history`/the summary/the message counter before the first cycle.
  This is the concrete implementation of §3's "cross-session static memory"
  placeholder, written speculatively and never given a mechanism until now.
- Separate from the episodic log (§4.2), by design: the log is an
  append-only audit trail, never overwritten; `WorkingMemorySnapshot` is a
  single current-state row per instance, overwritten (`update_or_create`)
  each shutdown, purely to seed the next boot. The log answers "what happened
  and why"; the snapshot answers "what should I remember right now."

**Note:** It does not store memory when running in autoreload mode (debugging mode where it restarts the server when files are updated). `RealtimeInterventionLLM` now accepts `restored_history_summary`/
`restored_participant_roles_summary` at construction and includes them in the
session's initial `instructions` at `connect()` time, once, not per-turn.
`Orchestrator._intervention_agent_for` supplies these from `wm` when creating
the agent — which works because `load_group_snapshot()` runs at boot, before
any message can arrive, so by the time the intervention agent is first
created (lazily, on the first incoming message), the restore has already
happened. Verified: a mocked snapshot's summary text is confirmed present in
the session's `instructions` payload.

**Still open**: what happens if the process dies without a clean shutdown
(crash, `kill -9`) — no snapshot gets written, so the next boot starts cold
despite the episodic log having a full record. Falling back to reconstructing
from recent `EpisodicLog` rows when no snapshot exists is the natural answer,
not built.

### 11.2 DM memory management (implemented)

**Built as sketched above**: `MainLLM.run_dm_management_cycle(wm)` — a
simpler sibling of `run_management_cycle`, dropping `participant_roles_summary`
entirely (a DM has exactly one participant, so there's nothing to track).
Plain-text response, not JSON-schema-constrained, since there's only one
field to produce. Wired into the orchestrator's existing DM early-return
branch (where the episodic-log skip already lived): every
`DM_MANAGEMENT_CYCLE_INTERVAL` (8, matching the group's cadence — same value
today, but a separate, independently-tunable constant, since there's no
reason a DM's pace must match the group's), `wm.apply_management_cycle()`
truncates that DM's history the same way the group's does (last-5 raw tail +
running summary), and `on_history_truncated()` re-syncs the intervention
agent's own `_sent_history_count` for that DM's session, same as the group
path. **Never logged anywhere** — the DM's summary lives only in that DM's
own in-memory WM, same privacy boundary as everything else in this scope; the
early-return this is nested inside is the same one that already skips
`EpisodicLog` for DMs.

Verified via a mocked test: a DM's history truncates correctly at the
configured interval while a group message processed in the *same* run leaves
the group's WM and the episodic log completely untouched (0 DM-originated log
rows) — the concern being tested was specifically whether reusing the same
shared `MainLLM` instance for both group and DM summarization could leak
private content across scopes. It can't, structurally: `MainLLM` is fully
stateless per call (each call builds its request fresh from whichever `wm`
object is passed in; nothing accumulates on `self` between calls), and `wm`
is always the scope-specific instance from `Orchestrator._wms`. The DM's
content does still leave the process over the network to OpenAI for
summarization — no different from what already happens generating a DM's
replies — it just never touches `EpisodicLog` or the group's `WorkingMemory`.

Left as documented above, still not decided: the cadence (currently just
matches the group's 8, arbitrarily) and whether the main LLM is even the
right choice here long-term (chosen for consistency with the proven group
pattern, not because the lighter-model quality issue that motivated moving
the group's version to the main LLM was re-tested for this simpler,
roles-free case).

---

## 12. On-demand summarization (implemented)

A user asking the bot to summarize the conversation is the natural motivating
case for actually *reading back* long-term memory — everything before this
was write-only (the episodic log had never been queried by anything but a
human via `manage.py shell`). **`EpisodicLog` is the long-term memory source
used when a user asks for a summary.**

**`provide_summary` is a conversational strategy, and it involves RAG** — in
the sense described below, not a proper RAG pipeline (see retrieval shape).
Structurally different from the other strategies: its `prompt_template`
can't rely on the normal last-20-messages history render, since the point is
surfacing something outside that window. `Orchestrator._handle_conversation_event`
retrieves before invoking the main LLM, landing the result in
`wm.retrieved_context` (a transient, per-turn field, cleared like
`forced_context` after) — the main LLM reads it only when this strategy fires.

**Why retrieval and the answer are two different steps, not one.**
`retrieved_context` is raw material — the literal past conversation
transcript for the retrieved rows — not a summary. Dispatching it verbatim
would just re-print old messages at the user rather than answer "summarize
what we talked about." The main LLM's job is the *generation* half of
retrieval-augmented generation: read the raw retrieved rows and produce an
actual condensed, organized, human-readable answer from them
(`provide_summary.yaml`'s `prompt_template` says exactly this: "write it for
a human to read: clear, well-organized, and easy to skim"). This isn't a
special case either — every strategy already works this way: the
intervention agent only ever decides *whether* to act and hands over
grounding material (`prompt_fragment`, `forced_context`, `history_summary`,
now `retrieved_context`); the main LLM is the only component that ever writes
user-facing text, in every case, not just this one.

**Retrieval shape — implemented**: `bot/discord_adapter.py::fetch_recent_episodic_log`
returns the most recent `SUMMARY_RETRIEVAL_LIMIT` (50) `EpisodicLog` rows for
the channel, chronological order, excluding `management_cycle` rows (they
have no `incoming_event_content`, not useful raw material) — no relevance
ranking or semantic search, purely recency-windowed. This is deliberately not
a proper RAG pipeline: a real one would search for content *relevant to the
specific question*; this returns the same window regardless of what's being
asked, so a fact outside the 50-row window is simply unreachable. Accepted
for now, per explicit confirmation; revisit if the fixed N proves
insufficient at real usage volume.

**Retrieval need generalized to an orthogonal signal (implemented) — and a
clear statement of what that does and doesn't mean.** A separate strategy,
`recall_detail` (a pointed question about one earlier fact, distinct from
`provide_summary`'s full recap), was built and then **merged back into
`respond_when_addressed`**: the trigger (respond to being addressed) and the
retrieval need (does answering require looking something up) turned out to
be independent questions, and encoding every combination as its own strategy
doesn't scale as more retrieval sources get added. Instead, `decide()` now
returns two independent booleans alongside the strategy id (§1):

- **`needs_history`** — implemented and acted on. When true (on any strategy,
  in practice mostly `respond_when_addressed`) or when `strategy_id ==
  "provide_summary"` (forced true regardless of what the model reports, same
  deterministic-override spirit as the cooldown veto), the orchestrator runs
  the exact retrieval described above and populates `wm.retrieved_context`.
  **This is still the same recency-window retrieval, not RAG yet ** — adding
  the flag did not add relevance ranking; see the previous paragraph's
  limitation, which applies here identically.
- **`needs_web_search`** — **captured only, not implemented yet.** The
  intervention agent is instructed to set this when a question needs current
  information from outside the conversation, but nothing reads the flag or
  performs a search. No web search capability exists anywhere in this
  codebase. It exists purely so how often this comes up is visible
  (`[MULCA debug]` logging) before deciding whether to build it.

To be unambiguous, since this is easy to overstate: **no proper RAG pipeline
(embeddings, semantic search, or any relevance ranking) and no web search
exist in this codebase.** What exists is (a) a recency-window database query
for `needs_history`, and (b) an unused boolean for `needs_web_search`. Real
options for closing the RAG gap, cheapest first, are noted earlier in this
document's design discussion: LLM-assisted keyword extraction (near-free,
reuses what the model already produces), SQLite full-text search, or true
embedding-based semantic search (the only one that's "real RAG," and the only
one needing new infrastructure). None are built.

**Scope of "summarize" when ambiguous — decided, not implemented**: a bare
"summarize what we've talked about" was meant to default to **today's
session**, with an explicit "summarize *everything*" as the broader,
unbounded signal. **Not built** — the implementation always fetches the same
fixed 50-row window regardless of phrasing; there's no date-range query yet
distinguishing the two cases.

**Two different summaries, two different prompts, two different models
(implemented).** The management cycle's internal summary is written by the
**main LLM** (moved there from the intervention agent, §11) — and so, as it
turns out, is `provide_summary`'s user-facing response, also the main LLM.
The distinction that matters isn't *which* model (both ended up being the
main LLM) but *which prompt and purpose*: `run_management_cycle` optimizes
for density or an LLM to read next cycle; `provide_summary`'s
`prompt_template` explicitly asks for something written for a human to read,
using the retrieved raw log content rather than the compressed internal
summary. The intervention agent's only role in either case is judging that a
summary was requested and selecting the strategy — it authors neither summary.

**DMs — resolved.** No special handling needed: a DM's WM is never persisted
to `EpisodicLog` by design (per "Channel/instance scoping"), so
`provide_summary`'s retrieval would simply find nothing there. Treated as a
natural no-op, not something worth building explicit blocking logic for.

**Still open**:
- Does "summarize everything" need to reach across a full multi-day
  deployment (the 10-group user study running over time)? Not yet exercised
  at that scale — the "fairly high N" retrieval window hasn't been sized
  against real log volume. Accepted as-is for now.

**New idea, not yet designed: a management cycle for `EpisodicLog` itself.**
Everything in §11 operates on WM (in-memory, per-session). A parallel
question for later: should there be a periodic process that tidies/
consolidates the *persisted* long-term store the same way, rather than
leaving `provide_summary`'s retrieval to brute-force a recency window forever
as the log grows? This is the actual fix for this section's recency-vs-relevance
limitation (a well-consolidated log needs less blunt windowing) — flagged for
a future pass, not scoped now.


