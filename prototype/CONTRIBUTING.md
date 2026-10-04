# Adding to MULCA

This is a task-oriented guide: "I want to add X, show me how." For *why*
things are structured this way, see `../BLUEPRINT.md`. For what's currently
implemented, see `README.md`.

## Instantiating with different personas/tasks/strategies

Persona, task, and which strategies are active are **three independent
choices**, all made in one place: MUCA-Server's `muca_server/run_server.py`.
Nothing here derives from anything else — picking a task doesn't
automatically pick strategies for it, and vice versa.

- **`TASK_ID`** (a constant near the top of the file) picks which
  MUCA-Server's `muca_server/cognition/config/tasks/*.yaml` file loads. Set it to the filename without
  `.yaml`.
- **`ACTIVE_STRATEGY_IDS`** (a list, same file) picks which strategies from
  the full pool (MUCA-Server's `muca_server/cognition/config/strategies/*.yaml`) are actually switched on.
  An id in the list that doesn't match any file fails loudly at boot.
- **Persona** is not yet a swap-by-constant choice — see "Adding a persona"
  below for the current (hardcoded-filename) mechanism.

**Current catalog, as of this writing** (check the actual files/constants if
this drifts — this list is a snapshot, not a live source of truth):

| Kind | Available | Currently active (`run_server.py`) |
|---|---|---|
| Task | `general_moderation`, `consensus_ranking` | `general_moderation` |
| Strategy | `participation_equality`, `respond_when_addressed`, `non_offensive`, `provide_summary`, `keep_on_topic` | all except `keep_on_topic` (which only makes sense paired with `consensus_ranking` — see its file's own comment) |
| Persona | one intervention persona, one main persona (no alternates yet) | both, always (see "Adding a persona") |

To switch scenarios (e.g. to run the `consensus_ranking` use case instead):
edit `TASK_ID` to `"consensus_ranking"` and add `"keep_conversation_on_topic"`
to `ACTIVE_STRATEGY_IDS`, then restart the bot. No other code changes needed
— this is the concrete test that the config-driven design (BLUEPRINT.md §9)
actually holds up.

## Adding a strategy

Strategies are the fixed, config-defined behaviors the intervention agent can
select. All of them live as flat YAML files in MUCA-Server's `muca_server/cognition/config/strategies/`.

1. Create a new file there, e.g. MUCA-Server's `muca_server/cognition/config/strategies/my_strategy.yaml`:

   ```yaml
   id: my_strategy
   trigger_description: >
     Plain-language description of when this should fire. This is what the
     intervention agent actually reads to decide -- be concrete, and mention
     which computed variables (if any) are relevant to check.
   trigger_variables: []   # or a list of keys from trigger_variables.py's output
   cooldown_messages: 5    # optional, 0/omitted = no cooldown
   trigger_threshold:      # optional -- gives the LLM a concrete number instead of vague language
     variable: gini_index
     min: 0.3
   prompt_template: |
     What the main LLM should do when this strategy fires. {prompt_fragment}
     is filled in with the intervention agent's own parameterized instruction.
   ```

   Two real examples to copy from, deliberately different shapes:
   - `participation_equality.yaml` — variable-driven (`gini_index` etc.),
     has both a threshold and a cooldown.
   - `non_offensive.yaml` or `respond_when_addressed.yaml` — `trigger_variables: []`,
     judged purely from reading the conversation, no cooldown (see the
     comment in `respond_when_addressed.yaml` for why some strategies
     deliberately have none).

2. **Add the id to `ACTIVE_STRATEGY_IDS` in MUCA-Server's `muca_server/run_server.py`.**
   A strategy sitting in the pool but not in that list has zero effect — this
   is intentional (BLUEPRINT.md §9: persona/task/strategies are three
   independent choices), but it's the one step that's easy to forget. An id
   listed there that doesn't match any file fails loudly at load time.

3. **On `trigger_variables`**: this list is documentation shown to the
   intervention agent (which computed signals are relevant to *this*
   strategy) — it does not filter what data the agent receives. The full
   `trigger_variables.py` output is always sent every cycle regardless. Set
   it to `[]` for anything that needs actual judgment over conversation
   content rather than a number (offensive language, "is this addressed to
   me," topic drift) — don't invent a fake variable just to have something
   to list.

4. **`cooldown_messages`**: message-count-based, not wall-clock (BLUEPRINT.md
   §10.5 — deliberately, applies identically to text and audio). Give one to
   anything unsolicited/nagging-prone. Leave it at 0 for anything that should
   be able to fire on consecutive messages (a direct-response strategy) or
   that shouldn't be suppressed just because it just fired (a safety
   intervention).

## Adding a persona

Persona files are plain YAML with one `persona:` key holding a text block —
see MUCA-Server's `muca_server/cognition/config/personas/intervention_default.yaml` and `main_default.yaml`.

Unlike strategies/tasks, persona loading is **not** yet a swap-by-constant
pattern — `build_app()` in `run_server.py` hardcodes which two files it
reads (`load_persona("main_default")`, `load_persona("intervention_default")`).
To add an alternative persona, create the new YAML file, then point those
calls at it (or generalize them to a
`PERSONA_ID`-style constant, matching how `TASK_ID` already works, if you're
adding more than one alternative). This asymmetry is a known gap, not a
design choice worth preserving — improving it is a reasonable first PR.

## Adding a task

Task files are plain YAML with one `description:` key — see
MUCA-Server's `muca_server/cognition/config/tasks/general_moderation.yaml` and `consensus_ranking.yaml`.

This one *is* a clean swap: create the new file, then set `TASK_ID` in
`run_server.py` to its filename (without `.yaml`). Remember: activating a
task doesn't activate any strategies for it — those are independent
(`ACTIVE_STRATEGY_IDS`, see above). `keep_conversation_on_topic` only makes
sense alongside `consensus_ranking`, for example, but nothing enforces that
pairing automatically; you turn both on deliberately.

## Adding a trigger variable

This is the one extension point that touches Python, not just config —
trigger variables are plain deterministic code, never an LLM call
(BLUEPRINT.md §2 step 3, "why" explained there).

1. Add the computation to MUCA-Server's `muca_server/cognition/trigger_variables.py`'s
   `compute_trigger_variables()`, and include it in the returned dict.
2. That's it for making it *available* — the whole dict is always sent to the
   intervention agent every cycle. To make a specific strategy's catalog
   entry mention it, add its key to that strategy's `trigger_variables:` list
   (documentation only, see above).
3. If your new variable needs the presence roster (who's in the channel, not
   just who's spoken) or needs to exclude the bot's own messages, follow the
   existing pattern in `compute_trigger_variables` rather than recomputing
   those from scratch.

## Conventions

- **Comments explain *why*, not *what*.** Every non-obvious choice in this
  codebase has a comment citing the tradeoff and, where relevant, a
  `BLUEPRINT.md §N` reference. If you're about to write a comment describing
  what the next line does, the code should probably just be clearer instead;
  if you're making a judgment call (why this default, why not the simpler
  alternative), write that down.
- **`# TODO: remove once live-tested`** marks temporary debug output
  (`print(...)` calls) added during active development against a live
  Discord/OpenAI connection. Leave these alone unless you're specifically
  cleaning up after confirming something works live — they're load-bearing
  for debugging, not accidental clutter.
- **Verification, given no guaranteed live credentials in every environment**:
  the established pattern is a one-off mocked async script (fake objects
  matching the shape of the real SDK/Discord API) run via `python -c "..."`
  or a scratch file, checked and discarded — not a formal pytest suite (none
  exists yet). Search recent git history / this file's sibling docs for
  examples of the pattern before inventing a new one. If something can only
  be verified live (a real API's actual behavior, not just your code's logic
  against a assumed shape), say so explicitly rather than claiming
  verification you didn't do — this codebase has hit real surprises this way
  (the Realtime API's Beta→GA migration) and the docs say so plainly rather
  than pretending otherwise.

## Guardrails — what to be more careful touching

- **WM field ownership** (BLUEPRINT.md §3's table): each field has exactly
  one designated writer. If you add a new WM field, document who writes it
  and when in the same style as the existing ones in
  MUCA-Server's `muca_server/cognition/working_memory.py`'s docstring/table — don't just add an attribute.
- **The orchestrator's per-cycle step order** (MUCA-Server's `muca_server/cognition/policy.py` (`CoalaPolicy`),
  BLUEPRINT.md §2): steps have invariants that depend on order (e.g. forced
  context and strategy output are mutually exclusive by construction because
  step 4 short-circuits step 5, not because of a runtime check). Reordering
  steps can silently break an invariant that isn't re-verified anywhere.
- **The `"channel:<id>"` vs `"dm:<user_id>"` scope split** (BLUEPRINT.md's
  "Channel/instance scoping" section): DM content must never reach the
  persisted episodic log or the snapshot — this is a privacy requirement,
  not just a routing detail. If you touch persistence (MUCA-Server's
  `muca_server/cognition/memory/`, `CoalaPolicy`), check `is_private`
  before writing.
