# Audio integration — open decisions

Working notes for the design discussion, not a spec. See `BLUEPRINT.md`
(§6, §10) for the full reasoning behind anything referenced below.

## Current plan, briefly

- One MULCA instance registers to one text channel + one voice channel
  (fixed pair); they share a single WM and a single intervention-agent
  session — genuinely one conversation, not two (BLUEPRINT.md's
  "Channel/instance scoping" section).
- The orchestrator already supports audio as a modality without further
  changes: `ConversationEvent(modality="audio", ...)` and
  `SpeechActivityEvent` both exist and funnel into the same per-scope queue
  as text (§6).
- Intent is **one unified intervention agent aware of both text and audio**
  (§10.1) — a single persistent Realtime session, not a separate one per
  modality.
- Multi-user voice-activity detection is planned to be **done ourselves**
  (tap Discord's per-user voice streams directly), not via the Realtime
  API's own turn detection — that's scoped to one speaker per session and
  can't tell which of several Discord participants is talking (§10.3).
- Self-interrupt (bot stops talking the instant someone else starts) is
  planned as a reflex that bypasses the normal per-scope queue entirely
  (§10.2) — a plain cancel action, no LLM judgment involved.
- An assertive "floor-claim" policy (deliberately holding the floor for ~1s
  when a strategy needs to interrupt a dominant speaker, rather than
  yielding instantly) has a sketched config shape (`turntaking:` block,
  §10.4) but is unbuilt.
- **Audio output (the bot actually speaking) is not designed at all yet** —
  `core/main_llm.py` only ever produces text today, regardless of what
  triggered it.

## Open decisions

### Audio output — the biggest unresolved piece
- [ ] Does the bot's spoken reply reuse `main_llm.py`'s existing text
  generation + bolt on TTS after, or does it need its own native-audio-
  generating implementation (e.g. driving the Realtime API's audio output
  modality directly)? Bolting TTS onto today's text-only path would
  effectively recreate the STT→LLM→TTS shape the original constraint rules
  out — just on the output side instead of the input side.
- [ ] Is there **one** Realtime session doing double duty (continuously
  listening *and* speaking), or **two** separate sessions/connections (one
  for the intervention agent's continuous listening, one dedicated to the
  main LLM's speech output)? This affects how self-interrupt (below) is
  actually wired.

### Input / listening
- [ ] Concretely, how do we tap Discord's per-user voice-receive streams for
  our own VAD? Which library/mechanism in discord.py's voice-receive support,
  and how do we distinguish speakers (per-SSRC or equivalent)?
- [ ] Should the *same* per-user VAD tap that produces `SpeechActivityEvent`
  also decide utterance boundaries for `ConversationEvent`, rather than
  relying on whatever the audio-understanding model's own segmentation does
  internally? (Currently §6 leaves boundary-detection as an unspecified
  internal detail of `AudioChannelAdapter` — this would tighten it to one
  mechanism instead of two.)

### Interruption / turn-taking
- [ ] Self-interrupt (§10.2): mechanically, what does "cancel the main LLM's
  in-flight response" actually call, once we know the answer to the
  one-session-vs-two question above?
- [ ] Floor-claim policy (§10.4): is `persist_seconds`/`retry_delay_seconds`
  actually implementable/testable without live voice, or does this need to
  wait until basic audio I/O works end-to-end first?
- [ ] §10.6's open item: should a *failed* floor-claim get a longer cooldown
  than a successful one, so a repeatedly-rebuffed interruption doesn't keep
  retrying on the same cadence?

### Scope / ownership
- [ ] Who's actually building `AudioChannelAdapter` — is this session's
  work superseding "colleague's component" from the original brief, or is
  this still Pietro's build with us firming up the interface?
- [ ] Does "open to DMs" (text) have any voice equivalent, or is voice always
  exactly the one registered group voice channel, never per-user?
- [ ] Reply routing once both modalities are live: does a reply always go
  back to the *same* channel/modality the triggering message came from, or
  does text-in/audio-out (or vice versa) ever make sense?

### Practical prerequisites (not design, but needed regardless)
- [ ] `PyNaCl` (voice encryption) and `ffmpeg` (audio encoding) aren't in
  `requirements.txt` yet — both are needed for discord.py voice support.
- [ ] Sequencing: get a minimal live voice connection working first and
  verify against real behavior, before layering VAD/turntaking design on
  top — same lesson learned from the text-side Realtime API surprise
  (Beta→GA deprecation) applies here: live APIs have edge cases no amount
  of design conversation catches in advance.
