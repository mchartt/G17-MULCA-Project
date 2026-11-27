import { parseAgentText, type Inline } from "../lib/agentText";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useEffect, useLayoutEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { faCompass, faPaperPlane } from "../lib/icons";
import type { Answer, Click, Person } from "../lib/types";
import { mentionParts, parseSlash, suggest } from "../lib/slash";
import { finishedLongAgo } from "./plan";
import { ProposalCard } from "./ProposalCard";
import { useNow } from "./useNow";
import { dotFor, nameOf, type Space } from "./space";

// "discord_voice": a line said in the Discord voice call, transcribed by MUCA-Server.
const CHANNEL_NAMES: Record<string, string> = { web: "Web", discord: "Discord", discord_voice: "Discord voice", slack: "Slack", calendar: "Calendar" };

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
  // A card about a task finished more than an hour ago leaves the chat (the Tasks page keeps the task).
  const now = useNow();
  const finished = new Set((space.state?.tasks ?? []).filter((t) => t.task_id && finishedLongAgo(t, now)).map((t) => t.task_id!));
  const aboutOldDoneTask = (p: { payload: Record<string, unknown> }) => {
    const id = p.payload?.task_id;
    return typeof id === "string" && finished.has(id);
  };
  // The box is one line and grows with what is typed (up to its max-height in the CSS).
  useLayoutEffect(() => {
    const el = input.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }, [draft]);

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
    <section className="chat" aria-label="Group chat" data-tour="chat">
      <div className="chat__log" role="log" aria-live="polite" aria-relevant="additions" aria-label="Messages" tabIndex={0}>
        {space.timeline.length === 0 && (
          <div className="chat__empty">
            <span className="chat__empty-mark" aria-hidden="true"><FontAwesomeIcon icon={faCompass} /></span>
            <p className="chat__empty-title">Say hello to your group.</p>
            <p>Talk normally. Cadence reads along and steps in only when it notices a coordination gap: no owner, a blocker, a decision going in circles. Nothing changes until one of you clicks.</p>
            <p className="muted small">To ask Cadence directly, start with <code>@coordinator</code>. Type <code>/</code> to see the commands.</p>
          </div>
        )}
        {space.timeline.map((item) =>
          item.kind === "proposal" ? (
            space.proposals[item.id] && !aboutOldDoneTask(space.proposals[item.id]) && (
              <ProposalCard
                key={`p-${item.id}`}
                proposal={space.proposals[item.id]}
                agentName={space.agentName}
                language={space.state?.language ?? ""}
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
      {/* Outside the log: announced once as a status, not again as a new log line. */}
      {space.thinking && <Thinking name={space.agentName} />}
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
      <form className="composer" onSubmit={send} data-tour="composer">
        <label htmlFor="composer-input" className="sr-only">Message to the group</label>
        <textarea
          id="composer-input"
          ref={input}
          rows={1}
          value={draft}
          onChange={(e) => { setDraft(e.target.value); setPicked(0); }}
          onKeyDown={onKey}
          placeholder={disabled ? "Reconnecting…" : "Message the group"}
          disabled={disabled}
        />
        <button className="btn btn--primary btn--round" type="submit" aria-label="Send" disabled={disabled || !draft.trim()}><FontAwesomeIcon icon={faPaperPlane} /></button>
      </form>
    </section>
  );
}

/** A few ways of saying "working on it", one picked per answer so it does not read like a loop. */
export const THINKING_LINES = ["{name} is thinking…", "{name} is cooking…", "Let me see…", "{name} is looking at the plan…"];

/** Feedback while Cadence prepares an answer: three dots and a short line, in dark gray. */
export function Thinking({ name }: { name: string }) {
  const [line] = useState(() => THINKING_LINES[Math.floor(Math.random() * THINKING_LINES.length)]!.replace("{name}", name));
  return (
    <div className="thinking" role="status" data-testid="thinking">
      <span className="thinking__dots" aria-hidden="true"><span /><span /><span /></span>
      <span className="thinking__text">{line}</span>
    </div>
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
          {text ? <AgentReply text={text} /> : <p className="msg__text">…</p>}
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

/** Cadence's reply: paragraphs, lists and bold read from plain text (never HTML), then its sources apart. */
export function AgentReply({ text }: { text: string }) {
  const { blocks, sources } = parseAgentText(text);
  const show = (parts: Inline[]) => parts.map((p, n) => (p.bold ? <strong key={n}>{p.text}</strong> : <span key={n}>{p.text}</span>));
  return (
    <div className="msg__text msg__text--agent">
      {blocks.map((block, n) =>
        block.kind === "list" ? (
          <ul key={n} className="msg__list">{block.items.map((item, i) => <li key={i}>{show(item)}</li>)}</ul>
        ) : (
          <p key={n}>{show(block.parts)}</p>
        ),
      )}
      {sources && (
        <p className="msg__sources">
          <span className="msg__sources-label">{sources.label}:</span> {sources.text}
        </p>
      )}
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
