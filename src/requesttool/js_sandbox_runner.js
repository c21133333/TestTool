const fs = require("fs");
const vm = require("vm");

function readInput() {
  const data = fs.readFileSync(0, "utf8");
  return data ? JSON.parse(data) : {};
}

function safeStringify(value) {
  if (typeof value === "string") {
    return value;
  }
  try {
    return JSON.stringify(value);
  } catch (err) {
    return String(value);
  }
}

function buildContext(variables, logs) {
  const ctx = {
    get: (key) => variables[String(key)],
    set: (key, value) => {
      variables[String(key)] = value;
    },
    remove: (key) => {
      delete variables[String(key)];
    },
    has: (key) => Object.prototype.hasOwnProperty.call(variables, String(key)),
    log: (...args) => {
      logs.push(args.map(safeStringify).join(" "));
    },
  };
  const consoleProxy = {
    log: (...args) => ctx.log(...args),
  };
  const sandbox = {
    ctx,
    console: consoleProxy,
    require: undefined,
    process: undefined,
    Buffer: undefined,
    setTimeout: undefined,
    setInterval: undefined,
  };
  return vm.createContext(sandbox, {
    codeGeneration: { strings: false, wasm: false },
  });
}

function runScript(code, context, timeoutMs) {
  const script = new vm.Script(String(code || ""), {
    filename: "script-processor.js",
  });
  script.runInContext(context, { timeout: timeoutMs });
}

function main() {
  const payload = readInput();
  const variables = payload.variables && typeof payload.variables === "object" ? payload.variables : {};
  const logs = [];
  const timeout = Math.min(1000, Number(payload.timeout) || 1000);
  const context = buildContext(variables, logs);
  runScript(payload.code, context, timeout);
  process.stdout.write(JSON.stringify({ variables, logs }));
}

try {
  main();
} catch (err) {
  const message = err && err.message ? err.message : String(err);
  process.stderr.write(message);
  process.exit(1);
}
