import { ProposalCard } from "../console/ProposalCard";
import { dotFor } from "../console/space";
import { useSampleCard } from "./sampleCard";
import { BUSY, DAYS, DAY_END, DAY_START, MEETING_CARD, MEETING_SLOTS, MEMBERS, freeForAll, freeHours, hourLabel, slotLabel, type Slot } from "./sample";

const SPAN = DAY_END - DAY_START;
const WEEK_HOURS = DAYS.length * SPAN;
const place = (from: number, to: number) => ({ left: `${((from - DAY_START) / SPAN) * 100}%`, width: `${((to - from) / SPAN) * 100}%` });
const range = (from: number, to: number) => `${hourLabel(from)} to ${hourLabel(to)}`;

/**
 * Planning with the members' calendars: the gaps everyone shares, and a card
 * that offers them. Cadence sees busy and free only, and a member picks.
 */
export function PlanWeek() {
  const [card, answer, last] = useSampleCard(MEETING_CARD);
  const free = freeForAll(BUSY);
  const chosen: Slot | null = card.status === "applied" && last?.option !== undefined ? MEETING_SLOTS[last.option] ?? null : null;
  const isChosen = (s: Slot) => chosen !== null && s.day === chosen.day && s.from === chosen.from;

  return (
    <>
      <header className="preview__head">
        <h1>Plan around real calendars.</h1>
        <p>
          When the group needs a meeting or a date, Cadence looks at the calendars the members connected and offers the hours that are free
          for everyone. It sees busy and free, never what an event is.
        </p>
      </header>

      <div className="plan">
        <div className="plan__side">
          <section className="panel-card plan__week" aria-labelledby="week-title">
            <h2 id="week-title">Week of 23 November</h2>
            <p className="legend">
              <span><i className="swatch swatch--busy" /> Busy</span>
              <span><i className="swatch swatch--free" /> Free for everyone</span>
              <span className="muted">Each bar is one day, 9:00 to 19:00.</span>
            </p>
            <div className="week__scroll">
              <table className="week">
                <caption className="sr-only">Busy hours of each member and the hours free for everyone, Monday 23 to Friday 27 November</caption>
                <thead>
                  <tr>
                    <th scope="col"><span className="sr-only">Member</span></th>
                    {DAYS.map((d) => <th key={d} scope="col">{d}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {MEMBERS.map((m) => (
                    <tr key={m.id}>
                      <th scope="row"><span className="dot" style={{ background: dotFor(m.id, MEMBERS) }} aria-hidden="true" /> {m.name}</th>
                      {DAYS.map((d, day) => {
                        const blocks = BUSY[m.id].filter(([at]) => at === day);
                        return (
                          <td key={d}>
                            <div className="lane" aria-hidden="true">
                              {blocks.map(([, from, to]) => <i key={from} className="lane__busy" style={place(from, to)} />)}
                            </div>
                            <span className="sr-only">{blocks.length ? `busy ${blocks.map(([, from, to]) => range(from, to)).join(", ")}` : "free all day"}</span>
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                  <tr className="week__all">
                    <th scope="row">Everyone free</th>
                    {DAYS.map((d, day) => {
                      const slots = free.filter((s) => s.day === day);
                      return (
                        <td key={d}>
                          <div className="lane lane--free" aria-hidden="true">
                            {slots.map((s) => <i key={s.from} className={`lane__free${isChosen(s) ? " lane__free--chosen" : ""}`} style={place(s.from, s.to)} />)}
                          </div>
                          <span className="week__slot">
                            {slots.length ? slots.map((s) => `${hourLabel(s.from)}–${hourLabel(s.to)}${isChosen(s) ? " · chosen" : ""}`).join(", ") : "none"}
                          </span>
                        </td>
                      );
                    })}
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          <section className="panel-card plan__hours" aria-labelledby="hours-title">
            <h2 id="hours-title">Free hours this week</h2>
            <ul className="bars">
              {MEMBERS.map((m) => {
                const hours = freeHours(BUSY[m.id]);
                return (
                  <li key={m.id}>
                    <span className="bars__name"><span className="dot" style={{ background: dotFor(m.id, MEMBERS) }} aria-hidden="true" /> {m.name}</span>
                    <span className="bars__track" aria-hidden="true"><i style={{ width: `${(hours / WEEK_HOURS) * 100}%` }} /></span>
                    <span className="bars__value">{hours} h</span>
                  </li>
                );
              })}
            </ul>
            <p className="muted small">Cadence uses this, with your profile, to suggest who could take a task and to say why. It never assigns: a member confirms.</p>
          </section>
        </div>

        <div className="plan__side">
          <ProposalCard proposal={card} title="Find a time" agentName="Cadence" onAnswer={answer} memberName={(id) => MEMBERS.find((m) => m.id === id)?.name ?? "a member"} />
          {chosen && (
            <p className="plan__done" role="status">
              Added to the plan: report meeting, {slotLabel(chosen)}–{hourLabel(chosen.to)}. It appears in every connected calendar.
            </p>
          )}
        </div>
      </div>
    </>
  );
}
