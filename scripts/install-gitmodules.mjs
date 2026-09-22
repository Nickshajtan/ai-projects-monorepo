#!/usr/bin/env node
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const args = new Set(process.argv.slice(2));
const force = args.has("--force") || args.has("-f");
const statusOnly = args.has("--status-only");

for (const arg of args) {
  if (!["--force", "-f", "--status-only"].includes(arg)) {
    console.error(`Unknown argument: ${arg}`);
    console.error("Usage: node scripts/install-gitmodules.mjs [--force] [--status-only]");
    process.exit(2);
  }
}

function run(command, commandArgs, options = {}) {
  const result = spawnSync(command, commandArgs, {
    cwd: options.cwd ?? repoRoot,
    encoding: "utf8",
    stdio: options.capture ? "pipe" : "inherit",
  });

  if (result.error) {
    throw new Error(`${command} failed: ${result.error.message}`);
  }
  if (result.status !== 0) {
    const details = options.capture ? `\n${result.stderr.trim()}` : "";
    throw new Error(`${command} ${commandArgs.join(" ")} exited ${result.status}${details}`);
  }
  return options.capture ? result.stdout.trim() : "";
}

function git(commandArgs, options = {}) {
  return run("git", commandArgs, options);
}

function parseGitmodules() {
  if (!existsSync(join(repoRoot, ".gitmodules"))) {
    throw new Error(`No .gitmodules file found at ${repoRoot}`);
  }

  const output = git(["config", "--file", ".gitmodules", "--get-regexp", "^(submodule\\..*\\.(path|url))$"], {
    capture: true,
  });
  const modules = new Map();

  for (const line of output.split(/\r?\n/).filter(Boolean)) {
    const firstSpace = line.indexOf(" ");
    const key = line.slice(0, firstSpace);
    const value = line.slice(firstSpace + 1);
    const match = /^submodule\.(.+)\.(path|url)$/.exec(key);
    if (!match) {
      continue;
    }
    const [, name, field] = match;
    const entry = modules.get(name) ?? { name };
    entry[field] = value;
    modules.set(name, entry);
  }

  return [...modules.values()].filter((entry) => entry.path && entry.url);
}

function expectedCommit(path) {
  const output = git(["ls-files", "--stage", "--", path], { capture: true });
  const match = /^160000\s+([0-9a-f]{40})\s+\d+\t/.exec(output);
  return match ? match[1] : null;
}

function pathState(path) {
  if (!existsSync(join(repoRoot, path))) {
    return "missing";
  }

  const result = spawnSync("git", ["-C", path, "rev-parse", "--is-inside-work-tree"], {
    cwd: repoRoot,
    encoding: "utf8",
    stdio: "pipe",
  });

  return result.status === 0 && result.stdout.trim() === "true"
    ? "git-checkout"
    : "non-git-path";
}

function currentCommit(path) {
  try {
    return git(["-C", path, "rev-parse", "HEAD"], { capture: true });
  } catch {
    return null;
  }
}

function printStatus(modules) {
  for (const module of modules) {
    const expected = expectedCommit(module.path);
    const state = pathState(module.path);
    if (state === "non-git-path") {
      console.log(`!${expected ?? "unknown"} ${module.path} (path exists but is not a Git checkout)`);
      continue;
    }
    const current = currentCommit(module.path);
    const marker = !current ? "-" : current === expected ? " " : "+";
    console.log(`${marker}${current ?? expected ?? "unknown"} ${module.path}`);
  }
}

function installModule(module) {
  const expected = expectedCommit(module.path);
  if (!expected) {
    throw new Error(`No gitlink entry found for ${module.path}`);
  }

  const state = pathState(module.path);
  if (state === "missing") {
    console.log(`Cloning ${module.path}...`);
    git(["clone", module.url, module.path]);
  } else if (state === "non-git-path") {
    throw new Error(
      `${module.path} exists but is not a Git checkout; move it aside or initialize it before installing submodules`
    );
  }

  git(["-C", module.path, "remote", "set-url", "origin", module.url]);

  const current = currentCommit(module.path);
  if (current === expected && !force) {
    console.log(`${module.path} already at ${expected}`);
    return;
  }

  const hasCommit = spawnSync("git", ["-C", module.path, "cat-file", "-e", `${expected}^{commit}`], {
    cwd: repoRoot,
    encoding: "utf8",
  }).status === 0;

  if (!hasCommit) {
    console.log(`Fetching ${module.path}...`);
    git(["-C", module.path, "fetch", "--tags", "origin"]);
  }

  console.log(`Checking out ${module.path} at ${expected}...`);
  git(["-C", module.path, "checkout", force ? "--force" : "--detach", expected]);
}

try {
  const modules = parseGitmodules();
  if (statusOnly) {
    printStatus(modules);
    process.exit(0);
  }

  for (const module of modules) {
    installModule(module);
  }

  console.log("Submodule status:");
  printStatus(modules);
} catch (error) {
  console.error(error.message);
  process.exit(1);
}
