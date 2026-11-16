// Copy the pinned pdf.js worker next to the static export so the cockpit can
// load it same-origin. Generated; never edit web/public/vendor by hand.
import { copyFileSync, mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const source = join(dirname(require.resolve("pdfjs-dist/package.json")), "build", "pdf.worker.min.mjs");
const target = join(dirname(fileURLToPath(import.meta.url)), "..", "public", "vendor", "pdf.worker.min.mjs");
mkdirSync(dirname(target), { recursive: true });
copyFileSync(source, target);
console.log(`pdf.js worker -> ${target}`);
