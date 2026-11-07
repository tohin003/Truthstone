// Loads every flag config listed under "flagkit"."configs" in package.json; exit 1 if one is invalid.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { ConfigError, loadConfig } from "../src/config.ts";

const root = new URL("../", import.meta.url);
const manifest = JSON.parse(readFileSync(new URL("package.json", root), "utf8")) as { flagkit?: { configs?: string[] } };
let failed = 0;
for (const path of manifest.flagkit?.configs ?? []) {
  try {
    const config = loadConfig(fileURLToPath(new URL(path, root)));
    console.log(`ok    ${path} (${config.flags.size} flags)`);
  } catch (error) {
    if (!(error instanceof ConfigError)) {
      throw error;
    }
    console.log(`FAIL  ${error.message}`);
    failed += 1;
  }
}
process.exitCode = failed === 0 ? 0 : 1;
