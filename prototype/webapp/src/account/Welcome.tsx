import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { TagInput, withPending } from "../console/TagInput";
import { saveProfile, type User } from "../lib/account";
import { ApiError } from "../lib/api";
import { faArrowLeft, faArrowRight, faCircleCheck, faPlus, faUsers } from "../lib/icons";
import { codeInAddress } from "../lib/invite";
import { JoinForm } from "./Home";
import { ProjectSetup } from "./ProjectSetup";

/** The steps, in order. The first three are the profile, saved at the end of "skills". */
export type WelcomeStep = "name" | "background" | "skills" | "ready" | "create" | "join";
const PROFILE: WelcomeStep[] = ["name", "background", "skills"];

/** A profile counts as filled once it says something Cadence can use to suggest owners. */
export const profileDone = (user: User) => !!user.discipline.trim() || user.skills.length > 0 || !!user.background?.trim();

type Props = {
  user: User;
  start: WelcomeStep;
  disabled: boolean;
  onUser: (user: User) => void;
  onEnter: (spaceToken: string) => void;
  /** Leave the guided setup for the plain home (spaces, create, join). */
  onSkip: () => void;
};

/**
 * The first minutes after signing up, one question per screen (tutor, 18 Nov:
 * "the first screen should ask me about my profile or to set up a project,
 * then the option to invite team members"). Profile → "your profile is set
 * up" → create or join a project. Every step can be skipped and changed
 * later from "Your profile".
 */
export function Welcome({ user, start, disabled, onUser, onEnter, onSkip }: Props) {
  const [step, setStep] = useState<WelcomeStep>(start);
  const [name, setName] = useState(user.displayName);
  const [discipline, setDiscipline] = useState(user.discipline);
  const [background, setBackground] = useState(user.background ?? "");
  const [skills, setSkills] = useState(user.skills);
  const [pending, setPending] = useState("");
  const [hours, setHours] = useState(user.weeklyHours === null ? "" : String(user.weeklyHours));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);

  // Each new screen moves the focus to its question, so a screen reader reads it.
  useEffect(() => heading.current?.focus(), [step]);

  const index = PROFILE.indexOf(step);
  const back = (): WelcomeStep | null => (index > 0 ? PROFILE[index - 1]! : step === "create" || step === "join" ? "ready" : null);

  async function next(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (step !== "skills") return setStep(PROFILE[index + 1]!);
    setBusy(true);
    try {
      onUser(await saveProfile({ displayName: name, discipline, skills: withPending(skills, pending), weeklyHours: hours === "" ? null : Number(hours), background }));
      setStep("ready");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Your profile was not saved. Try again.");
    } finally {
      setBusy(false);
    }
  }

  const invited = codeInAddress() !== "";
  const createChoice = (
    <button key="create" className="choice" onClick={() => setStep("create")}>
      <span className="choice__icon"><FontAwesomeIcon icon={faPlus} /></span>
      <strong>Create a project</strong>
      <span className="muted small">Name it, describe it, add the brief. Then invite your team.</span>
    </button>
  );
  const joinChoice = (
    <button key="join" className="choice" onClick={() => setStep("join")}>
      <span className="choice__icon"><FontAwesomeIcon icon={faUsers} /></span>
      <strong>Join a project</strong>
      <span className="muted small">{invited ? "You have an invite: the code is already filled in." : "A teammate already created it and sent you a code."}</span>
    </button>
  );

  const title = (text: string) => <h1 ref={heading} tabIndex={-1} className="welcome__title">{text}</h1>;
  const previous = back();

  let body: ReactNode;
  if (index >= 0) {
    body = (
      <form className="welcome__form" onSubmit={next}>
        {step === "name" && (
          <>
            {title("What should your group call you?")}
            <p className="welcome__lead">This is the name your teammates and Cadence will use.</p>
            <label htmlFor="w-name">Your name</label>
            <input id="w-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={40} required autoComplete="name" placeholder="e.g. Sara Rossi" />
          </>
        )}
        {step === "background" && (
          <>
            {title("What do you bring to the group?")}
            <p className="welcome__lead">A line about what you study and what you have done before. It helps Cadence suggest who could take a task.</p>
            <label htmlFor="w-discipline">What you study</label>
            <input id="w-discipline" value={discipline} onChange={(e) => setDiscipline(e.target.value)} maxLength={100} placeholder="e.g. Computer Science and Engineering" />
            <label htmlFor="w-background">Your background, in your own words</label>
            <textarea id="w-background" rows={4} maxLength={600} value={background} onChange={(e) => setBackground(e.target.value)} placeholder="e.g. Two years of web development, I built the front end of a small app. I'd like to try user research." />
          </>
        )}
        {step === "skills" && (
          <>
            {title("Which skills can you offer?")}
            <p className="welcome__lead">Add a few, one at a time. Press Enter after each.</p>
            <label htmlFor="w-skills">Skills</label>
            <TagInput id="w-skills" tags={skills} onChange={setSkills} onPending={setPending} placeholder="e.g. React, Figma, user interviews" />
            <label htmlFor="w-hours">Hours a week for the project <span className="muted">(optional)</span></label>
            <input id="w-hours" type="number" min={0} max={80} value={hours} onChange={(e) => setHours(e.target.value)} placeholder="e.g. 8" />
            <p className="muted small">Cadence uses this only to suggest owners. No scores, no rankings, never shared outside your groups.</p>
          </>
        )}
        {error && <p className="form__error" role="alert">{error}</p>}
        <div className="welcome__nav">
          {previous && <button type="button" className="btn btn--soft" onClick={() => setStep(previous)}><FontAwesomeIcon icon={faArrowLeft} /> Back</button>}
          <button className="btn btn--primary" type="submit" disabled={busy}>
            {busy ? "Saving…" : step === "skills" ? "Save my profile" : "Continue"} <FontAwesomeIcon icon={faArrowRight} />
          </button>
        </div>
      </form>
    );
  } else if (step === "ready") {
    body = (
      <div className="welcome__ready">
        <span className="welcome__check" aria-hidden="true"><FontAwesomeIcon icon={faCircleCheck} /></span>
        {title("Don't worry, your profile is set up.")}
        <p className="welcome__lead">You can change it any time from “Your profile”. Now, a project to work on.</p>
        {/* Arriving from an invite link, joining comes first: the code is already filled in. */}
        <div className="welcome__choices">
          {invited ? <>{joinChoice}{createChoice}</> : <>{createChoice}{joinChoice}</>}
        </div>
      </div>
    );
  } else {
    body = (
      <>
        {title(step === "create" ? "Tell Cadence about your project." : "Join your team.")}
        <p className="welcome__lead">
          {step === "create"
            ? "Cadence reads this once to propose the goal, the deliverables and the milestones. You confirm them in the chat."
            : "Paste the invite code a teammate sent you."}
        </p>
        {step === "create" ? <ProjectSetup disabled={disabled} onEnter={onEnter} /> : <JoinForm title="Invite code" disabled={disabled} onEnter={onEnter} />}
        <div className="welcome__nav">
          <button type="button" className="btn btn--soft" onClick={() => setStep("ready")}><FontAwesomeIcon icon={faArrowLeft} /> Back</button>
        </div>
      </>
    );
  }

  const phase = index >= 0 ? 0 : step === "ready" ? 1 : 2;
  return (
    <section className="welcome" aria-label="Getting started">
      <div className="welcome__top">
        <ol className="welcome__progress" aria-label="Setup progress">
          {["Your profile", "Ready", "Your project"].map((label, i) => (
            <li key={label} className={i < phase ? "is-done" : i === phase ? "is-current" : undefined} aria-current={i === phase ? "step" : undefined}>
              {label}
            </li>
          ))}
        </ol>
        <button className="btn btn--link btn--small" onClick={onSkip}>Skip for now</button>
      </div>
      <div className="welcome__stage" key={step}>
        {index >= 0 && <p className="welcome__count">Step {index + 1} of 3</p>}
        {body}
      </div>
    </section>
  );
}
