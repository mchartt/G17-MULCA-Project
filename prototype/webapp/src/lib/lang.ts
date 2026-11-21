import type { Proposal } from "./types";

// The same short list MUCA-Server uses to tell an Italian text (wording.py):
// a card's own words are written in the group's language, so they say which
// language its labels and buttons should be in (live test 20/11: Italian
// cards had "Reject", "Why?", "What is late or at risk").
const ITALIAN_WORDS =
  /(^|[^\p{L}])(il|la|di|che|è|per|un|una|del|della|sono|chi|si|non|perché|anche|ma|sì|deve|dai|dal|questa|questo|prima|fallo|aggiungi|crea|collega|intervengo|dipende|serve|servono|grazie|ricevuto|bene|stasera|domani|oggi|ancora|fatto|ho|sto|va|procede|ciao|capito|perfetto)(?=$|[^\p{L}])/iu;

export type Lang = "en" | "it";

/** True when a sample of text reads as Italian. */
export function isItalian(sample: string): boolean {
  return ITALIAN_WORDS.test(sample);
}

/**
 * The language of a card: the one the group chose ("en" / "it"), else the
 * language of what Cadence wrote on it (reason, question, title, options).
 */
export function cardLang(proposal: Proposal, chosen = ""): Lang {
  if (chosen === "it" || chosen === "en") return chosen;
  const p = proposal.payload;
  const sample = [
    proposal.rationale,
    p.question,
    p.goal,
    p.title,
    ...(p.findings ?? []),
    ...(p.options ?? []).map((o) => `${o.label} ${o.argument ?? ""}`),
  ]
    .filter(Boolean)
    .join(" ");
  return isItalian(sample) ? "it" : "en";
}
