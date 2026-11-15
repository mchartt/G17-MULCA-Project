# Methods: HCI, design process, requirements (UNG), scenarios
Type: support · Version: v2 (2026-10-07) · Source: Lesson 1 (L1) slides 19–23; Lesson 2 (L2) slides 4–50, 95–107

## HCI and UX
HCI: design, evaluation, implementation of interactive systems for people (ACM SIGCHI); user at the centre (L1 s20); multidisciplinary (L1 s22–23). UX: how well and happily users interact (L1 s19). Success: usability, utility, engagement, robustness, adoption (L1 s21).

## Development process
- Waterfall is NOT linear (L2 s4–5); Boehm's spiral iterates with risk analysis and prototypes (L2 s6).
- HCI adds to each phase: requirements of ALL stakeholders, UX design, prototyping, UX evaluation (L2 s7–8).
- Interaction design: user-centred, iterative (L2 s11–12). Lifecycle (Preece et al.): requirements ↔ UX design ↔ prototyping ↔ evaluation (L2 s13).
- Design Thinking: empathize, define, ideate, prototype, test; non-linear (L2 s14–15).

## Elicitation
- Exploring stakeholders' goals, needs, expectations. Hard: they poorly understand their needs and the technology. Listen; focus on problems, not solutions; communicate constraints (L2 s17).
- User research (R. Tassi's slides on WeBeep, L2 s18): foundational – understand needs (contextual interviews, shadowing, diary studies); generative – the right design (participatory design, concept critique); evaluative – the design right (experience prototyping) (L2 s21–24).
- Techniques: interviews (rich, few experts; time-consuming) (L2 s27); questionnaires (large samples, quantifiable; keep short; shallow) (L2 s28); focus groups (3–20 stakeholders + moderator, ~2h; only "public" opinions) (L2 s29); contextual observation (tacit knowledge; Hawthorne effect) (L2 s30).
- Biases → remedies: ease of recall → directed and "why" questions (L2 s32); analyst overconfidence → scenario reflection, counter-arguments (L2 s33); faulty reasoning → devil's advocate (L2 s34); communication and motivational biases → pre-elicitation: purpose, key terms, use of data, confidentiality (L2 s35–37).
- Synthesis: research setup → conduction → synthesis (L2 s39); unstructured raw data → a model (concepts, terms, notation, rules) to share with stakeholders and specify for implementors (L2 s40–42).

## UNG model
UNG = USERS NEEDS GOALS, the course's model of user requirements (L2 s43).
- A stakeholder (an end user is-a stakeholder) has [1,N] needs (with sub-needs), in [1,N] contexts (physical, social, organizational); wants to achieve [1,N] goals (with sub-goals) with technology; a goal satisfies [1,N] needs and has constraints (space, resource, time, other) (L2 s44).
- Stakeholders: primary users (frequent use), secondary (occasional, or via others), tertiary (affected, or influence adoption). End users = primary + secondary (L2 s45).
- Need: a lack of something requisite, desirable or useful for the user (L2 s46) – a property of the users. Goal: what the system achieves for the user (improve a task or capability, reduce a burden) (L2 s47) – a property of the system (L2 s50). Context: where, and at which step of the user's activity (L2 s48). Constraint: what can't change (resources, time, politics, competition, technology, users' special deficits); capture early (L2 s49).
- E.g. autistic children need to develop communication skills and not be bored (needs) → game-based linguistic tasks (goal). Needs can conflict (L2 s50).

## Scenarios
- A "story about use" (Carroll 2002): one situation of use by a typical user (persona), refined with stakeholders (L2 s95). Kin of use cases, user stories, storyboards (L2 s97).
- Used across the lifecycle (L2 s98); kinds: requirements, design, prototype, demo, evaluation (L2 s99).
- Design scenario: 1 user profile, 2 goals, 3 context, 4 tasks as a textual or visual narrative (L2 s101–103, s105–106). In conversational interaction the task flow is a dialogue; with other modes, model one general flow (L2 s104).
- Strong: specific actor and goal, context and constraints, observable steps, failures, a meaningful outcome, evidence or labelled assumptions. Avoid: feature lists, early UI detail, generic users, only the happy path, one scenario as proof, never revising (L2 s107).
