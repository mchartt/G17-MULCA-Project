import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { faCompass, faPaperPlane } from "../lib/icons";
import type { Answer, Click, Person } from "../lib/types";
import { mentionParts, parseSlash, suggest } from "../lib/slash";
import { ProposalCard } from "./ProposalCard";
import { dotFor, nameOf, type Space } from "./space";

const CHANNEL_NAMES: Record<string, string> = { web: "Web", discord: "Discord", slack: "Slack", calendar: "Calendar" };

type Props = {
  space: Space;
  onSay: (text: string) => void;
  /** A line that starts with "/": run it, never send it to the group. */
  onCommand: (text: string) => void;
  onAnswer: (proposalId: string, click: Click) => Promise<Answer>;
  disabled: boolean;
};

export function Chat({ space, onSay, onCommand, onAnswer, disabled }: Props) {
  const [draft, setDraft] = useState("");
  const input = useRef<HTMLTextAreaElement>(null);
  // Commands after "/", Cadence and the teammates after "@", offered while typing.
  const teammates = space.members.filter((m) => m.id !== space.me?.id).map((m) => m.name);
  const hints = suggest(draft, teammates);
  // Which suggestion Enter or Tab takes: moved with the arrow keys.
  const [picked, setPicked] = useState(0);
  const pick = hints[Math.min(picked, hints.length - 1)];
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [space.timeline]);

  function send(e?: FormEvent) {
    e?.preventDefault();
    if (!draft.trim() || disabled) return;
    if (parseSlash(draft)) onCommand(draft);
    else onSay(draft);
    setDraft("");
  }

  function fill(text: string) {
    setDraft(text);
    setPicked(0);
    input.current?.focus();
  }

  function onKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (pick && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
      e.preventDefault();
      setPicked((Math.min(picked, hints.length - 1) + (e.key === "ArrowDown" ? 1 : hints.length - 1)) % hints.length);
      return;
    }
    // Tab always completes. Enter completes only a word still being typed
    // ("/che", "@mat"); a finished command ("/checkin") is sent as it is.
    if (pick && (e.key === "Tab" || (e.key === "Enter" && !e.shiftKey && pick.fill.trim() !== draft.trim()))) {
      e.preventDefault();
      fill(pick.fill);
      return;
    }
    if (e.key === "Escape" && pick) {
      setDraft("");
      return;
    }
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
            <p>Talk normally. Cadence reads along and steps in only when it notices a coordination gap: no owner, a blocker, a decision going in circles. Nothing changes until one of you clicks.</p>
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
      {hints.length > 0 && (
        <ul className="hints" aria-label="Suggestions">
          {hints.map((h) => (
            <li key={h.label} className={h === pick ? "hints__picked" : undefined}>
              <button type="button" onClick={() => fill(h.fill)}>
                <code>{h.label}</code> <span className="muted">{h.about}</span>
                {h === pick && <kbd>Enter</kbd>}
              </button>
            </li>
          ))}
        </ul>
      )}
      <form className="composer" onSubmit={send}>
        <label htmlFor="composer-input" className="sr-only">Message to the group</label>
        <textarea
          id="composer-input"
          ref={input}
          rows={2}
          value={draft}
          onChange={(e) => { setDraft(e.target.value); setPicked(0); }}
          onKeyDown={onKey}
          placeholder={disabled ? "Reconnecting…" : "Message the group, @ to address Cadence or a teammate, / for commands"}
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
        <p className="msg__text">{withMentions(text, space.members.map((m) => m.name))}</p>
      </div>
    </div>
  );
}

/** The message with @coordinator and every @Teammate shown as a tag, so the group sees who was addressed. */
function withMentions(text: string, people: string[]) {
  return mentionParts(text, people).map((part, n) => (part.mention ? <span key={n} className="mention">{part.text}</span> : part.text));
}

export function initials(name: string): string {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]!.toUpperCase()).join("") || "?";
}
