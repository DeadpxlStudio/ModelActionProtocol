import { createRequire } from "node:module";
import { runVerify } from "./verify.js";
import { dim, bold, cyan } from "./tty.js";

const require = createRequire(import.meta.url);
// Resolves to packages/cli/package.json at runtime — dist/index.js → ../package.json
const cliPkg = require("../package.json") as { name: string; version: string };

const HELP = `${bold("map")} ${dim("— Model Action Protocol CLI")}

${bold("Usage")}
  map verify <ledger.json>        Verify a ledger file
  map verify -                    Verify a ledger from stdin
  map verify <ledger> --json      Emit machine-readable JSON
  map info                        Print CLI + spec versions
  map --version                   Print CLI version
  map --help                      Print this help

${bold("Examples")}
  map verify ./agent.ledger.json
  cat ./agent.ledger.json | map verify -
  map verify ./agent.ledger.json --json | jq

${bold("Web verifier")}
  ${cyan("https://verify.modelactionprotocol.org")}
`;

export async function run(argv: string[]): Promise<number> {
  const args = argv.slice(2);

  if (args.length === 0 || args[0] === "--help" || args[0] === "-h") {
    process.stdout.write(HELP);
    return 0;
  }

  if (args[0] === "--version" || args[0] === "-v") {
    process.stdout.write(`${cliPkg.name} ${cliPkg.version}\n`);
    return 0;
  }

  if (args[0] === "info") {
    const { MAP_VERSION, MAP_PROTOCOL } = await import("@model-action-protocol/core");
    process.stdout.write(`${cliPkg.name} ${cliPkg.version}\n`);
    process.stdout.write(`spec: ${MAP_PROTOCOL} ${MAP_VERSION}\n`);
    return 0;
  }

  const command = args[0];

  if (command === "verify") {
    const positional = args.slice(1).filter((a) => !a.startsWith("--"));
    const flags = new Set(args.slice(1).filter((a) => a.startsWith("--")));
    const input = positional[0];
    if (!input) {
      process.stderr.write("error: `map verify` requires a path or `-` for stdin\n\n");
      process.stdout.write(HELP);
      return 2;
    }
    return runVerify(input, { json: flags.has("--json") });
  }

  process.stderr.write(`error: unknown command "${command}"\n\n`);
  process.stdout.write(HELP);
  return 2;
}
