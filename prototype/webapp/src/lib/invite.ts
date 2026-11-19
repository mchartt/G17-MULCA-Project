/**
 * The invite link of a space: it opens the login page with the code filled
 * in (account/Home.tsx reads it), so a teammate only has to click "Join".
 */
export function inviteLink(code: string): string {
  return `${location.origin}/login?code=${encodeURIComponent(code)}`;
}

/** Copies a text; false when the browser refuses (the text stays on screen to copy by hand). */
export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}
