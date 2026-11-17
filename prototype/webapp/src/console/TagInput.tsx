import { useState, type KeyboardEvent } from "react";

type Props = { id: string; tags: string[]; onChange: (tags: string[]) => void; placeholder?: string; max?: number };

/** What is typed and not yet a tag still counts: call this when the form is sent. */
export function withPending(tags: string[], pending: string, max = 20): string[] {
  const all = [...tags];
  for (const part of pending.split(",").map((s) => s.trim()).filter(Boolean)) {
    if (!all.some((t) => t.toLowerCase() === part.toLowerCase())) all.push(part.slice(0, 40));
  }
  return all.slice(0, max);
}

/**
 * A list of short tags (skills). Enter or a comma turns what was typed into
 * a tag; Backspace in the empty box removes the last one; each tag has its
 * own remove button. `onPending` lets the form include text not yet a tag.
 */
export function TagInput({ id, tags, onChange, placeholder, max = 20, onPending }: Props & { onPending?: (text: string) => void }) {
  const [text, setText] = useState("");

  const set = (value: string) => {
    setText(value);
    onPending?.(value);
  };
  const commit = (value: string) => {
    onChange(withPending(tags, value, max));
    set("");
  };

  function onKey(e: KeyboardEvent<HTMLInputElement>) {
    if ((e.key === "Enter" || e.key === ",") && text.trim()) {
      e.preventDefault();
      commit(text);
    } else if (e.key === "Backspace" && !text && tags.length) {
      onChange(tags.slice(0, -1));
    }
  }

  return (
    <div className="tags">
      {tags.map((tag) => (
        <span key={tag} className="tags__tag">
          {tag}
          <button type="button" aria-label={`Remove ${tag}`} onClick={() => onChange(tags.filter((t) => t !== tag))}>×</button>
        </span>
      ))}
      <input
        id={id}
        value={text}
        onChange={(e) => (e.target.value.includes(",") ? commit(e.target.value) : set(e.target.value))}
        onKeyDown={onKey}
        onBlur={() => text.trim() && commit(text)}
        placeholder={tags.length ? "" : placeholder}
        maxLength={200}
      />
    </div>
  );
}
