import type { CatchUp, CatchUpChannel, MemberId } from "../lib/types";
import { Dialog } from "./Dialogs";

const CHANNEL_NAMES: Record<string, string> = { web: "the web space", discord: "Discord", slack: "Slack" };
const time = (unix: number) => new Date(unix * 1000).toLocaleString(undefined, { weekday: "short", hour: "2-digit", minute: "2-digit" });

type Props = { open: boolean; summary: string; catchup: CatchUp | null; inviteCode: string; nameOf: (id?: MemberId | null) => string | undefined; onClose: () => void };

function Messages({ place, title }: { place: CatchUpChannel; title: string }) {
  return (
    <section aria-label={title}>
      <h3>{title}</h3>
      {place.total > place.messages.length && <p className="muted small">{place.total - place.messages.length} earlier messages not shown.</p>}
      <ul className="catchup__messages">
        {place.messages.map((m, i) => (
          <li key={i}>
            <span className="muted small">{time(m.at)}</span> <strong>{m.speaker === "coordinator" ? "Cadence" : m.speaker}</strong>: {m.text}
          </li>
        ))}
      </ul>
    </section>
  );
}

/**
 * "What did I miss?" (CS12): the decisions taken and the messages written in
 * the group's other channels since this member's last catch-up. Everything
 * shown comes from the decision log and the channels' own history: the
 * coordinator writes no summary of its own here, so nothing is invented.
 */
export function CatchUpDialog({ open, summary, catchup, inviteCode, nameOf, onClose }: Props) {
  return (
    <Dialog open={open} title="Catch up" onClose={onClose}>
      <div className="catchup">
        <p role="status">{summary || "Asking the coordinator…"}</p>

        {catchup && !catchup.linked && (
          <p className="muted">
            To link a channel, write <code>/coordinator link {inviteCode}</code> in your group's Discord or Slack channel.
          </p>
        )}

        {catchup && catchup.decisions.length > 0 && (
          <section aria-labelledby="catchup-decisions">
            <h3 id="catchup-decisions">Decided while you were away</h3>
            <ul className="catchup__decisions">
              {catchup.decisions.map((d) => (
                <li key={`${d.question}-${d.decided_at}`}>
                  <strong>{d.choice}</strong>
                  <span className="muted"> · {d.question}</span>
                  {d.reason && <p className="muted small">{d.reason}</p>}
                </li>
              ))}
            </ul>
          </section>
        )}

        {catchup && ((catchup.tasks_done?.length ?? 0) > 0 || (catchup.tasks_added?.length ?? 0) > 0) && (
          <section aria-labelledby="catchup-tasks">
            <h3 id="catchup-tasks">In the plan</h3>
            <ul className="catchup__decisions">
              {catchup.tasks_done?.map((t) => <li key={`d-${t.task_id}`}><strong>Done:</strong> {t.title}{t.owner_id ? <span className="muted"> · {nameOf(t.owner_id) ?? "a member"}</span> : null}</li>)}
              {catchup.tasks_added?.map((t) => <li key={`a-${t.task_id}`}><strong>New:</strong> {t.title}{t.owner_id ? <span className="muted"> · {nameOf(t.owner_id) ?? "a member"}</span> : null}</li>)}
            </ul>
          </section>
        )}

        {catchup?.here && catchup.here.messages.length > 0 && <Messages place={catchup.here} title="In this chat" />}

        {catchup?.elsewhere.filter((place) => place.messages.length > 0).map((place) => (
          <Messages key={place.channel} place={place} title={`On ${CHANNEL_NAMES[place.channel] ?? place.channel}`} />
        ))}

        <div className="form__actions">
          <button type="button" className="btn btn--primary" onClick={onClose}>Done</button>
        </div>
      </div>
    </Dialog>
  );
}
