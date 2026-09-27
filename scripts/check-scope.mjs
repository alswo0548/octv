// Lightweight guard for this UI-only delivery. This is not a security audit.
import { readdir, readFile } from "node:fs/promises";
import { join } from "node:path";
const roots = ["frontend/web/src", "frontend/mobile/src", "shared/src"];
const files = ["frontend/mobile/App.tsx"];
async function walk(dir) {
  for (const e of await readdir(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) await walk(p);
    else if (/\.(tsx?|jsx?)$/.test(p)) files.push(p);
  }
}
for (const root of roots) await walk(root);
const rules = [
  ["network call", /\b(fetch|XMLHttpRequest|WebSocket|EventSource)\s*\(/],
  [
    "network/identity/persistence dependency",
    /from\s+['"][^'"]*(axios|supabase|firebase|async-storage|secure-store|jsonwebtoken|bcrypt|next-auth|msw)[^'"]*['"]/i,
  ],
  [
    "persistent browser state",
    /\b(localStorage|sessionStorage|indexedDB)\b|document\.cookie/,
  ],
  [
    "native external action",
    /\bLinking\s*\.|\b(expo-location|expo-notifications)\b/,
  ],
  [
    "automatic input validation",
    /\b(required|pattern|minLength|maxLength)\s*(=|[}\s>])/,
  ],
  ["business calculation", /\.(sort|reduce)\s*\(/],
];
const failures = [];
for (const file of files) {
  const source = await readFile(file, "utf8");
  for (const [name, pattern] of rules)
    if (pattern.test(source)) failures.push(`${file}: ${name}`);
  for (const form of source.matchAll(/<form\b[^>]*>/g))
    if (!form[0].includes("noValidate"))
      failures.push(`${file}: form must disable browser validation`);
}
if (failures.length) {
  console.error(failures.join("\n"));
  process.exit(1);
}
console.log(
  `UI scope guard passed (${files.length} source files). Manual review remains necessary.`,
);
