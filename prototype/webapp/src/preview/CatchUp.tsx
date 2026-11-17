import { Message } from "../console/Chat";
import { ProposalCard } from "../console/ProposalCard";
import { emptySpace, type Space } from "../console/space";
import { useSampleCard } from "./sampleCard";
import { LAB_CARD, ME, MEMBERS, MISSED, THURSDAY, THURSDAY_DECISION } from "./sample";

const SPACE: Space = { ...emptySpace, members: MEMBERS, me: ME };
const memberName = (id: number | string) => MEMBERS.find((m) => m.id === id)?.name ?? "a member";
const noAnswer = async () => ({ type: "notice" as const, ok: true, text: "" });

/**
 * The cross-channel story: a decision taken on Discord on Thursday reaches
 * the member who was absent, on the web, on Monday, with its source.
 */
export function CatchUp() {
  const [lab, answer] = useSampleCard(LAB_CARD);
  return (
    <>
      <header className="preview__head">
        <h1>Miss a call, not a decision.</h1>
        <p>
          The group decides on Discord while one member is away. Days later she asks Cadence from the web space and gets what concerns her,
          with where and when it was said.
        </p>
      </header>

      <div className="story">
        <section className="story__col" aria-labelledby="story-thu">
          <h2 id="story-thu">Thursday 19 Nov <span className="tag">Discord · Ada is away</span></h2>
          {THURSDAY.slice(0, 2).map((m) => <Message key={m.text} space={SPACE} author={m.author} text={m.text} channel={m.channel} mine={false} />)}
          <ProposalCard proposal={THURSDAY_DECISION} agentName="Cadence" onAnswer={noAnswer} memberName={memberName} />
          <Message space={SPACE} author={null} channel="discord" mine={false} text="Decided: think-aloud with 5 users, chosen by Chiara. It is in the decision log." />
          {THURSDAY.slice(2).map((m) => <Message key={m.text} space={SPACE} author={m.author} text={m.text} channel={m.channel} mine={false} />)}
        </section>

        <section className="story__col" aria-labelledby="story-mon">
          <h2 id="story-mon">Monday 23 Nov <span className="tag">Web space · private to Ada</span></h2>
          <Message space={SPACE} author={ME} text="@coordinator what did I miss on Thursday?" channel="web" mine />
          <div className="panel-card missed">
            <p className="msg__who"><span className="msg__agent-label">Cadence</span><span className="tag">Coordinator</span></p>
            <p>You were not in Thursday's call on Discord (40 minutes; Bruno, Chiara and Dario were). Two things concern you:</p>
            <ol>
              {MISSED.map((m) => (
                <li key={m.title}>
                  {m.title}
                  <span className="muted small">Source: {m.source}</span>
                </li>
              ))}
            </ol>
          </div>
          <ProposalCard proposal={lab} agentName="Cadence" onAnswer={answer} memberName={memberName} />
          <p className="muted small">This answer is private. It reads the group's memory and adds nothing to it; the task changes only if Ada clicks.</p>
        </section>
      </div>
    </>
  );
}
