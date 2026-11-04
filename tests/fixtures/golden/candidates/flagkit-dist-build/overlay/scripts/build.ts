// Builds dist/ from src/: Node's own type stripper, then relative imports re-pointed at .js files.
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { stripTypeScriptTypes } from "node:module";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const srcDir = join(root, "src");

/** The JavaScript that dist/ holds for one source file. */
export function compile(name: string, source: string): string {
  const stripped = stripTypeScriptTypes(source, { mode: "strip" });
  const relinked = stripped.replace(/(\bfrom\s+["']\.{1,2}\/[^"']+)\.ts(["'])/g, "$1.js$2");
  const body = relinked.replace(/[ \t]+$/gm, "").replace(/\n{3,}/g, "\n\n");
  return `// Generated from src/${name} by scripts/build.ts. Do not edit: run \`npm run build\`.\n${body}`;
}

function outputs(): Map<string, string> {
  const files = new Map<string, string>();
  for (const name of readdirSync(srcDir).sort()) {
    if (name.endsWith(".ts")) {
      files.set(name.replace(/\.ts$/, ".js"), compile(name, readFileSync(join(srcDir, name), "utf8")));
    }
  }
  return files;
}

const args = process.argv.slice(2);
const outAt = args.indexOf("--out");
const outDir = outAt >= 0 ? args[outAt + 1] : join(root, "dist");
const built = outputs();

if (args.includes("--check")) {
  const stale: string[] = [];
  for (const [name, text] of built) {
    const path = join(outDir, name);
    if (!existsSync(path) || readFileSync(path, "utf8") !== text) {
      stale.push(name);
    }
  }
  const extra = existsSync(outDir) ? readdirSync(outDir).filter((name) => name.endsWith(".js") && !built.has(name)) : [];
  if (stale.length > 0 || extra.length > 0) {
    const listed = [...stale.map((name) => `dist/${name} differs from src`), ...extra.map((name) => `dist/${name} has no source`)];
    console.error(`dist/ is out of date:\n  ${listed.join("\n  ")}\nRun \`npm run build\` and commit dist/.`);
    process.exitCode = 1;
  } else {
    console.log(`dist/ is up to date (${built.size} files).`);
  }
} else {
  mkdirSync(outDir, { recursive: true });
  for (const [name, text] of built) {
    writeFileSync(join(outDir, name), text);
  }
  console.log(`built ${built.size} files into ${outDir}`);
}
