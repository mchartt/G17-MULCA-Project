import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useRef, useState, type ClipboardEvent, type DragEvent, type FormEvent } from "react";
import { createMySpace } from "../lib/account";
import { ApiError, saveToken } from "../lib/api";
import { clearDraftBrief, composeBrief, draftBrief, savePendingBrief, type BriefDocument } from "../lib/brief";
import { DOCUMENT_TYPES, readDocument } from "../lib/documents";
import { faArrowRight, faFileLines, faXmark } from "../lib/icons";

type Props = {
  disabled: boolean;
  onEnter: (spaceToken: string) => void;
  /** The heading above the form; the wizard has its own. */
  title?: string;
};

const ACCEPTED = DOCUMENT_TYPES.split(",");
const accepted = (file: File) => ACCEPTED.some((ext) => file.name.toLowerCase().endsWith(ext));
const size = (bytes: number) => (bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`);
const kind = (name: string) => name.split(".").pop()?.toUpperCase() ?? "FILE";

/**
 * A new project: its name, what it is about, and the documents Cadence reads
 * once to draft the plan (the assignment, notes; the files are not kept). The space is created first, because
 * reading a document needs the space's token; then each file is read, and the
 * description and the documents go to the console, which hands them to Cadence
 * as the brief. Nothing is decided here: Cadence answers with a card.
 */
export function ProjectSetup({ disabled, onEnter, title }: Props) {
  const [name, setName] = useState("");
  // Pre-filled with what the member typed in the landing's prompt bar, if anything.
  const [description, setDescription] = useState(draftBrief);
  const [files, setFiles] = useState<File[]>([]);
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Set when the space exists but some documents could not be read.
  const [created, setCreated] = useState<string | null>(null);
  // The space is ready: a check is drawn for a moment, then the console opens.
  const [ready, setReady] = useState(false);
  const picker = useRef<HTMLInputElement>(null);

  function add(list: FileList | File[]) {
    const incoming = [...list];
    const refused = incoming.filter((f) => !accepted(f));
    setError(refused.length ? `${refused.map((f) => f.name).join(", ")}: only PDF, Word, PowerPoint, text or Markdown.` : null);
    setFiles((before) => [...before, ...incoming.filter((f) => accepted(f) && !before.some((b) => b.name === f.name && b.size === f.size))].slice(0, 6));
  }

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    add(e.dataTransfer.files);
  };
  const onPaste = (e: ClipboardEvent) => {
    if (e.clipboardData.files.length) {
      e.preventDefault();
      add(e.clipboardData.files);
    }
  };

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      setBusy("Creating the space…");
      const { token } = await createMySpace(name);
      saveToken(token);
      const read: BriefDocument[] = [];
      const failed: string[] = [];
      for (const [i, file] of files.entries()) {
        setBusy(`Reading ${file.name} (${i + 1} of ${files.length})…`);
        try {
          read.push(await readDocument(token, file));
        } catch {
          failed.push(file.name);
        }
      }
      const passed = savePendingBrief(token, composeBrief(description, read));
      clearDraftBrief();
      if (failed.length || !passed) {
        setCreated(token);
        setError(
          failed.length
            ? `The space is ready, but ${failed.join(", ")} could not be read. You can paste its text later from the setup card.`
            : "The space is ready, but the brief is too long to pass on from here. Paste it from the setup card in the space.",
        );
        return;
      }
      setReady(true);
      const still = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
      await new Promise((done) => setTimeout(done, still ? 0 : 450));
      onEnter(token);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setBusy(null);
    }
  }

  const off = disabled || busy !== null;
  return (
    <form className="panel-card form setup-form" onSubmit={submit} onPaste={onPaste}>
      {title && <h3>{title}</h3>}
      <label htmlFor="c-project">Project name</label>
      <input id="c-project" value={name} onChange={(e) => setName(e.target.value)} maxLength={80} required placeholder="e.g. AUI group project, team 17" />

      <label htmlFor="c-description">What is the project about?</label>
      <textarea
        id="c-description"
        rows={4}
        maxLength={4000}
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        placeholder="The course, what you have to deliver, the deadlines you know. The more precise you are, the better Cadence helps."
        aria-describedby="c-description-hint"
      />
      <p id="c-description-hint" className="muted small">Be precise: Cadence uses this to propose the goal and milestones. You confirm them, nothing is decided for you.</p>

      <span className="form__label" id="c-docs-label">Documents Cadence can read <span className="muted">(optional)</span></span>
      <div
        className={`shelf${over ? " shelf--over" : ""}${busy || ready ? " shelf--sending" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={onDrop}
        aria-labelledby="c-docs-label"
        role="group"
      >
        {files.length > 0 && (
          <ul className="shelf__docs" aria-label="Documents added">
            {files.map((f, i) => (
              <li key={`${f.name}-${f.size}`} className="doc" style={{ ["--tilt" as string]: `${((i % 3) - 1) * 2.2}deg`, ["--i" as string]: i }}>
                <span className="doc__kind">{kind(f.name)}</span>
                <span className="doc__lines" aria-hidden="true"><i /><i /><i /><i /></span>
                <span className="doc__name" title={f.name}>{f.name}</span>
                <span className="doc__size muted">{size(f.size)}</span>
                <button type="button" className="doc__remove" aria-label={`Remove ${f.name}`} onClick={() => setFiles(files.filter((x) => x !== f))}>
                  <FontAwesomeIcon icon={faXmark} />
                </button>
              </li>
            ))}
          </ul>
        )}
        <button type="button" className="shelf__add" onClick={() => picker.current?.click()} disabled={off || files.length >= 6}>
          <FontAwesomeIcon icon={faFileLines} />
          <strong>{files.length ? "Add another document" : "Drop, paste or choose documents"}</strong>
          <span className="muted small">The assignment, notes, a brief. PDF, Word, PowerPoint or text, up to 10 MB each. Cadence reads their text once to draft the plan; the files are not kept.</span>
        </button>
        <input ref={picker} className="sr-only" type="file" multiple accept={DOCUMENT_TYPES} tabIndex={-1} aria-hidden="true" onChange={(e) => { if (e.target.files) add(e.target.files); e.target.value = ""; }} />
      </div>

      {error && <p className="form__error" role="alert">{error}</p>}
      {busy && <p className="muted small" role="status">{busy}</p>}
      {created ? (
        <button type="button" className="btn btn--primary" onClick={() => onEnter(created)}>Open the space <FontAwesomeIcon icon={faArrowRight} /></button>
      ) : (
        <button className={`btn btn--primary${ready ? " btn--ready" : ""}`} type="submit" disabled={off}>
          {ready ? (
            <>
              <svg className="check-draw" viewBox="0 0 16 16" aria-hidden="true"><path d="M4 8.4l2.6 2.6 5.4-6" /></svg> Ready
            </>
          ) : (
            <>{busy ? "One moment…" : "Create the space"} <FontAwesomeIcon icon={faArrowRight} /></>
          )}
        </button>
      )}
    </form>
  );
}
