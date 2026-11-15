// After `vite build`: copy the film frames into dist/film, so a static host
// (Vercel) serves the whole landing. The web adapter serves them itself too.
import { cpSync, existsSync } from "node:fs";

const from = "film/public";
if (existsSync(from)) {
  cpSync(from, "dist/film", { recursive: true });
  console.log("film copied to dist/film");
} else {
  console.warn("film/public not found: the landing will show its still version");
}
