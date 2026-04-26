#!/usr/bin/env node
import { run } from "../dist/index.js";

run(process.argv).then(
  (code) => process.exit(code ?? 0),
  (err) => {
    process.stderr.write(`map: ${(err && err.stack) || String(err)}\n`);
    process.exit(2);
  }
);
