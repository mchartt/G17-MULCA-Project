import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useRef, useState, type ClipboardEvent, type DragEvent, type FormEvent } from "react";
import { createMySpace } from "../lib/account";
import { ApiError, saveToken } from "../lib/api";
import { clearDraftBrief, composeBrief, draftBrief, savePendingBrief, type BriefDocument } from "../lib/brief";
import { DOCUMENT_TYPES, readDocument } from "../lib/documents";
import { faArrowLeft, faArrowRight, faFileLines, faXmark } from "../lib/icons";

type Props = {
  disabled: boolean;
  onEnter: (spaceToken: string) => void;
  /** Back to the home, without creating anything. */
  onBack: () => void;
};

const MAX_DOCS = 6;
const ACCEPTED = DOCUMENT_TYPES.split(",");
const accepted = (file: File) => ACCEPTED.some((ext) => file.name.toLowerCase().endsWith(ext));
const size = (bytes: number) => (bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`);
const kind = (name: string) => name.split(".").pop()?.toUpperCase() ?? "FILE";
/** Each sheet lies a little crooked, as on a real desk; the same file always lies the same way. */
const TILTS = [-2.6, 1.8, -1.2, 2.4, -1.9, 1.1];

/**
 * The setup desk (/login/new), a page of its own: the project's name and what
 * it is about on the notepad, the documents Cadence reads once laid on the
 * mat (the assignment, notes; the files are not kept). The space is created
 * first, because reading a document needs the space's token; then each file
 * is read, and the description and the documents go to the console, which
 * hands them to Cadence as the brief. Nothing is decided here: Cadence
 * answers with a card.
 */
export function ProjectDesk({ disabled, onEnter, onBack }: Props) {
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
    setFiles((before) => [...before, ...incoming.filter((f) => accepted(f) && !before.some((b) => b.name === f.name && b.size === f.size))].slice(0, MAX_DOCS));
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
  const full = files.length >= MAX_DOCS;
  return (
    <form className="desk" onSubmit={submit} onPaste={onPaste}>
      <header className="desk__head">
        <button type="button" className="btn btn--link btn--small" onClick={onBack} disabled={busy !== null}>
          <FontAwesomeIcon icon={faArrowLeft} /> Your projects
        </button>
        <h1 id="desk-title">Set up a new project</h1>
        <p className="desk__lead">Write what the project is and lay the documents on the desk. Cadence reads them once to propose the goal and the milestones; you confirm them in the chat.</p>
      </header>

      {/* The notepad: the name and the brief, in the member's own words. */}
      <div className="desk__pad">
        <label htmlFor="c-project">Project name</label>
        <input id="c-project" value={name} onChange={(e) => setName(e.target.value)} maxLength={80} required placeholder="e.g. AUI group project, team 17" />

        <label htmlFor="c-description">What is the project about?</label>
        <textarea
          id="c-description"
          maxLength={4000}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="The course, what you have to deliver, the deadlines you know. The more precise you are, the better Cadence helps."
          aria-describedby="c-description-hint"
        />
        <p id="c-description-hint" className="muted small">Nothing is decided for you: Cadence proposes, one of you confirms.</p>

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
      </div>

      {/* The mat: drop files anywhere on it, or choose them with the button. */}
      <div
        className={`mat${over ? " mat--over" : ""}${busy || ready ? " mat--sending" : ""}${files.length ? "" : " mat--empty"}${full ? " mat--full" : ""}`}
        onDragOver={(e) => { e.preventDefault(); if (!full) setOver(true); }}
        onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setOver(false); }}
        onDrop={onDrop}
        aria-labelledby="c-docs-label"
        role="group"
      >
        <div className="mat__bar">
          <span id="c-docs-label" className="mat__label">Documents <span className="mat__long">Cadence can read </span><span className="muted">(optional)</span></span>
          <span className="mat__count">{files.length} of {MAX_DOCS}</span>
        </div>

        {files.length > 0 ? (
          <ul className="mat__docs" aria-label="Documents added">
            {files.map((f, i) => (
              <li key={`${f.name}-${f.size}`} className="doc" style={{ ["--tilt" as string]: `${TILTS[i % TILTS.length]}deg`, ["--i" as string]: i }}>
                <span className="doc__kind">{kind(f.name)}</span>
                <span className="doc__lines" aria-hidden="true"><i /><i /><i /><i /><i /></span>
                <span className="doc__name" title={f.name}>{f.name}</span>
                <span className="doc__size muted">{size(f.size)}</span>
                <button type="button" className="doc__remove" aria-label={`Remove ${f.name}`} disabled={off} onClick={() => setFiles(files.filter((x) => x !== f))}>
                  <FontAwesomeIcon icon={faXmark} />
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <div className="mat__hint" aria-hidden="true">
            <span className="mat__ghost" /><span className="mat__ghost" /><span className="mat__ghost" />
            <p>{over ? "Let go to lay it on the desk." : "Drop the assignment, your notes or a brief here."}</p>
          </div>
        )}

        <div className="mat__tools">
          <button type="button" className="btn btn--soft" onClick={() => picker.current?.click()} disabled={off || full}>
            <FontAwesomeIcon icon={faFileLines} /> {files.length ? "Add a document" : "Choose documents"}
          </button>
          <p className="muted small">{full ? "The desk is full: remove one to add another." : "PDF, Word, PowerPoint or text, up to 10 MB each. You can also paste them. Read once, not kept."}</p>
        </div>
        <input ref={picker} className="sr-only" type="file" multiple accept={DOCUMENT_TYPES} tabIndex={-1} aria-hidden="true" onChange={(e) => { if (e.target.files) add(e.target.files); e.target.value = ""; }} />
      </div>
    </form>
  );
}
