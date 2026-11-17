import { useState } from "react";
import type { Answer, Click, Proposal } from "../lib/types";

/**
 * A sample card that behaves like a real one: the member's click is what
 * changes it (same rule as the server), but only on this page.
 */
export function useSampleCard(initial: Proposal): [Proposal, (click: Click) => Promise<Answer>, Click | null] {
  const [proposal, setProposal] = useState(initial);
  const [last, setLast] = useState<Click | null>(null);
  const answer = async (click: Click): Promise<Answer> => {
    if (click.action === "helpful") return { type: "notice", ok: true, text: "Thanks: Cadence keeps this as feedback only." };
    const status = click.action === "reject" ? "rejected" : click.action === "not_now" ? "snoozed" : "applied";
    setProposal({ ...proposal, status });
    setLast(click);
    return { type: "notice", ok: true, text: "" };
  };
  return [proposal, answer, last];
}
