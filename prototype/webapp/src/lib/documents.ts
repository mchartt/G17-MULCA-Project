// The text of a document a member uploads (PDF, Word, PowerPoint, text), read
// by the web adapter (POST /api/extract). The file is not kept anywhere.
import { ADAPTER_URL, ApiError } from "./api";

export const DOCUMENT_TYPES = ".pdf,.docx,.pptx,.txt,.md";
const MAX_BYTES = 10 * 1024 * 1024;

export async function readDocument(token: string, file: File): Promise<{ name: string; text: string; truncated: boolean }> {
  if (file.size > MAX_BYTES) throw new ApiError("The file is larger than 10 MB.");
  let res: Response;
  try {
    res = await fetch(`${ADAPTER_URL}/api/extract`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": file.type || "application/octet-stream",
        "X-File-Name": encodeURIComponent(file.name),
      },
      body: file,
    });
  } catch {
    throw new ApiError("Cadence can't be reached. Check your connection, then try again.");
  }
  if (res.ok) return res.json();
  let detail = "";
  try {
    detail = (await res.json()).detail;
  } catch {
    /* no explanation from the server */
  }
  throw new ApiError(typeof detail === "string" && detail ? detail : "The file could not be read.");
}
