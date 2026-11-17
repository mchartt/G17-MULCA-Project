import type { CatchUp } from "../lib/types";
import { Dialog } from "./Dialogs";

const CHANNEL_NAMES: Record<string, string> = { web: "the web space", discord: "Discord", slack: "Slack" };
const time = (unix: number) => new Date(unix * 1000).toLocaleString(undefined, { weekday: "short", hour: "2-digit", minute: "2-digit" });

type Props = { open: boolean; summary: string; catchup: CatchUp | null; inviteCode: string; onClose: () => void };

/**
 * "What did I miss?" (CS12): the decisions taken and the messages written in
 * the group's other channels since this member's last catch-up. Everything
 * shown comes from the decision log and the channels' own history: the
 * coordinator writes no summary of its own here, so nothing is invented.
 */
export function CatchUpDialog({ open, summary, catchup, inviteCode, onClose }: Props) {
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

        {catchup?.elsewhere.filter((place) => place.messages.length > 0).map((place) => (
          <section key={place.channel} aria-label={`Messages on ${CHANNEL_NAMES[place.channel] ?? place.channel}`}>
            <h3>On {CHANNEL_NAMES[place.channel] ?? place.channel}</h3>
            {place.total > place.messages.length && <p className="muted small">{place.total - place.messages.length} earlier messages not shown.</p>}
            <ul className="catchup__messages">
              {place.messages.map((m, i) => (
                <li key={i}>
                  <span className="muted small">{time(m.at)}</span> <strong>{m.speaker}</strong>: {m.text}
                </li>
              ))}
            </ul>
          </section>
        ))}

        <div className="form__actions">
          <button type="button" className="btn btn--primary" onClick={onClose}>Done</button>
        </div>
      </div>
    </Dialog>
  );
}
