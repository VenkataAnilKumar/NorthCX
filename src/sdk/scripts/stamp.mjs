// After a build: copy the script bundle into the backend package (which serves it) and stamp it with a hash of the sources,
// so a test can tell when the committed bundle is out of date.
import { createHash } from "node:crypto";
import { copyFileSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const src = join(root, "src");
const hash = createHash("sha256");
for (const f of readdirSync(src).sort()) hash.update(f).update(readFileSync(join(src, f)));
const stamp = hash.digest("hex").slice(0, 16);
const out = join(root, "..", "backend", "northcx", "static");
mkdirSync(out, { recursive: true });
const body = readFileSync(join(root, "dist", "northcx-widget.js"), "utf8");
writeFileSync(join(out, "northcx-widget.js"), `/* northcx-widget source:${stamp} */\n${body}`);
copyFileSync(join(root, "dist", "northcx-client.js"), join(out, "northcx-client.js"));
console.log(`widget bundle written (source ${stamp}, ${body.length} bytes)`);
