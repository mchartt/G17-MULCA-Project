import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { faCompass, faPaperPlane } from "../lib/icons";
import type { Answer, Click, Person } from "../lib/types";
import { ProposalCard } from "./ProposalCard";
import { dotFor, nameOf, type Space } from "./space";

const CHANNEL_NAMES: Record<string, string> = { web: "Web", discord: "Discord", slack: "Slack", calendar: "Calendar" };

type Props = {
  space: Space;
  onSay: (text: string) => void;
  onAnswer: (proposalId: string, click: Click) => Promise<Answer>;
  disabled: boolean;
};

export function Chat({ space, onSay, onAnswer, disabled }: Props) {
  const [draft, setDraft] = useState("");
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [space.timeline]);

  function send(e?: FormEvent) {
    e?.preventDefault();
    if (!draft.trim() || disabled) return;
    onSay(draft);
    setDraft("");
  }

  function onKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  return (
    <section className="chat" aria-label="Group chat">
      <div className="chat__log" role="log" aria-live="polite" aria-relevant="additions">
        {space.timeline.length === 0 && (
          <div className="chat__empty">
            <p>This is where the group talks. Cadence reads along and steps in only when the group needs it.</p>
            <p className="muted">Write @coordinator with a question to ask about the plan, the dates or the decisions. Type /planning or /checkin to run a command.</p>
          </div>
        )}
        {space.timeline.map((item) =>
          item.kind === "proposal" ? (
            space.proposals[item.id] && (
              <ProposalCard
                key={`p-${item.id}`}
                proposal={space.proposals[item.id]}
                agentName={space.agentName}
                memberName={(id) => nameOf(id, space) ?? "a member"}
                onAnswer={(click) => onAnswer(item.id, click)}
              />
            )
          ) : (
            <Message key={item.message.id} space={space} author={item.message.author} text={item.message.text} channel={item.message.channel} mine={item.message.author?.id === space.me?.id} />
          ),
        )}
        <div ref={end} />
      </div>
      <form className="composer" onSubmit={send}>
        <label htmlFor="composer-input" className="sr-only">Message to the group</label>
        <textarea
          id="composer-input"
          rows={2}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKey}
          placeholder={disabled ? "Reconnecting…" : "Message the group"}
          disabled={disabled}
        />
        <button className="btn btn--primary btn--round" type="submit" aria-label="Send" disabled={disabled || !draft.trim()}><FontAwesomeIcon icon={faPaperPlane} /></button>
      </form>
    </section>
  );
}

/** One chat bubble; also used by the preview screens (src/preview/). */
export function Message({ space, author, text, channel, mine }: { space: Space; author: Person | null; text: string; channel: string; mine: boolean }) {
  if (!author) {
    return (
      <div className="msg msg--agent">
        <span className="avatar avatar--agent" aria-hidden="true"><FontAwesomeIcon icon={faCompass} /></span>
        <div className="bubble">
          <p className="msg__who"><span className="msg__agent-label">{space.agentName}</span><span className="tag">Coordinator</span></p>
          <p className="msg__text">{text || "…"}</p>
        </div>
      </div>
    );
  }
  return (
    <div className={`msg${mine ? " msg--mine" : ""}`}>
      <span className="avatar" style={{ background: dotFor(author.id, space.members) }} aria-hidden="true">{initials(author.name)}</span>
      <div className="bubble">
        <p className="msg__who">
          {mine ? "You" : author.name}
          {channel !== "web" && <span className="tag">{CHANNEL_NAMES[channel] ?? channel}</span>}
        </p>
        <p className="msg__text">{text}</p>
      </div>
    </div>
  );
}

export function initials(name: string): string {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]!.toUpperCase()).join("") || "?";
}
