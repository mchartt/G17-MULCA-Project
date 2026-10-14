# Methods: HCI, design process, requirements (UNG), scenarios
Type: support · Version: v1 (2026-10-14) · Source: the teaching team's methods material

## HCI and UX
HCI: design, evaluation, implementation of interactive systems for people (ACM SIGCHI); user at the centre; multidisciplinary. UX: how well and happily users interact. Success: usability, utility, engagement, robustness, adoption.

## Development process
- Waterfall is NOT linear; Boehm's spiral iterates with risk analysis and prototypes.
- HCI adds to each phase: requirements of ALL stakeholders, UX design, prototyping, UX evaluation.
- Interaction design: user-centred, iterative. Lifecycle (Preece et al.): requirements ↔ UX design ↔ prototyping ↔ evaluation.
- Design Thinking: empathize, define, ideate, prototype, test; non-linear.

## Elicitation
- Exploring stakeholders' goals, needs, expectations. Hard: they poorly understand their needs and the technology. Listen; focus on problems, not solutions; communicate constraints.
- User research: foundational – understand needs (contextual interviews, shadowing, diary studies); generative – the right design (participatory design, concept critique); evaluative – the design right (experience prototyping).
- Techniques: interviews (rich, few experts; time-consuming); questionnaires (large samples, quantifiable; keep short; shallow); focus groups (3–20 stakeholders + moderator, ~2h; only "public" opinions); contextual observation (tacit knowledge; Hawthorne effect).
- Biases → remedies: ease of recall → directed and "why" questions; analyst overconfidence → scenario reflection, counter-arguments; faulty reasoning → devil's advocate; communication and motivational biases → pre-elicitation: purpose, key terms, use of data, confidentiality.
- Synthesis: research setup → conduction → synthesis; unstructured raw data → a model (concepts, terms, notation, rules) to share with stakeholders and specify for implementors.

## UNG model
UNG = USERS NEEDS GOALS, the course's model of user requirements (the UNG model is a deliverable, see the schedule).
- A stakeholder (an end user is-a stakeholder) has [1,N] needs (with sub-needs), in [1,N] contexts (physical, social, organizational); wants to achieve [1,N] goals (with sub-goals) with technology; a goal satisfies [1,N] needs and has constraints (space, resource, time, other).
- Stakeholders: primary users (frequent use), secondary (occasional, or via others), tertiary (affected, or influence adoption). End users = primary + secondary.
- Need: a lack of something requisite, desirable or useful for the user – a property of the users. Goal: what the system achieves for the user (improve a task or capability, reduce a burden) – a property of the system. Context: where, and at which step of the user's activity. Constraint: what can't change (resources, time, politics, competition, technology, users' special deficits); capture early.
- E.g. autistic children need to develop communication skills and not be bored (needs) → game-based linguistic tasks (goal). Needs can conflict.

## Scenarios
- A "story about use" (Carroll 2002): one situation of use by a typical user (persona), refined with stakeholders. Kin of use cases, user stories, storyboards.
- Used across the lifecycle; kinds: requirements, design, prototype, demo, evaluation.
- Design scenario: 1 user profile, 2 goals, 3 context, 4 tasks as a textual or visual narrative. In conversational interaction the task flow is a dialogue; with other modes, model one general flow.
- Strong: specific actor and goal, context and constraints, observable steps, failures, a meaningful outcome, evidence or labelled assumptions. Avoid: feature lists, early UI detail, generic users, only the happy path, one scenario as proof, never revising.
