# Claude CLI Spawn Findings

Date: 2026-09-23

Context: benchmark target qualification for `benchmarks/ai-doc-benchmark` on native Windows, from inside an existing Codex CLI session.

## Installed CLI

PowerShell resolves Claude CLI to:

```text
C:\Users\38098\.local\bin\claude.exe
```

Observed version after login/update:

```text
2.1.280 (Claude Code)
```

`claude doctor` reports:

```text
Running: native (2.1.280)
Platform: win32-x64
Path: C:\Users\38098\.local\bin\claude.exe
Config install method: native
Search: OK (bundled)
```

## Authentication

`claude auth status` reported:

```json
{
  "loggedIn": true,
  "authMethod": "claude.ai",
  "apiProvider": "firstParty",
  "apiKeySource": "/login managed key"
}
```

No `CLAUDE_*` or `ANTHROPIC_*` environment variables were required for the qualified run.

## Non-Interactive Mode

The installed CLI help states:

```text
Claude Code - starts an interactive session by default, use -p/--print for non-interactive output
```

Working headless command shape:

```text
C:\Users\38098\.local\bin\claude.exe --print --output-format json --model sonnet --permission-mode bypassPermissions "Implement task.md"
```

The JSON result reports the effective canonical model as:

```text
claude-sonnet-5
```

## Permission Behavior

The qualified target uses:

```text
--permission-mode bypassPermissions
```

This allowed Claude to read `task.md`, edit files in the current working directory, run validation commands, and exit without interactive prompts.

No separate sandbox flag was used. The benchmark relies on its disposable copied Git workspace for isolation.

## Direct Preflight

Disposable workspace:

```text
D:\AI\projects\.tmp-claude-preflight
```

Prompt:

```text
Implement task.md
```

Result:

- process exited `0`;
- JSON result reported `terminal_reason: completed`;
- `claude-preflight-output.txt` was created;
- filesystem verification confirmed the requested content.

## Qualified Target Shape

Target config used:

```text
benchmarks/ai-doc-benchmark/runs/smoke-claude-sonnet-5-bypass-target.json
```

Target command:

```json
{
  "command": "C:\\Users\\38098\\.local\\bin\\claude.exe",
  "args": [
    "--print",
    "--output-format",
    "json",
    "--model",
    "sonnet",
    "--permission-mode",
    "bypassPermissions"
  ],
  "model": "claude-sonnet-5",
  "tool_version": "claude-code 2.1.280"
}
```

## Qualification Evidence

Single benchmark qualification observation:

```text
benchmarks/ai-doc-benchmark/runs/smoke-20260923-claude-sonnet-5-original-qualification/smoke-20260923-claude-original-qualification/
```

Observed:

- `target_started: true`
- termination: `completed`
- exit code: `0`
- validity: `valid`
- grader: `completed`
- workspace diff modified `src/api_contract.py` from `users` to `accounts`

Four-treatment smoke evidence root:

```text
benchmarks/ai-doc-benchmark/runs/smoke-20260923-claude-sonnet-5/
```

All four smoke observations completed with exit code `0`, valid observation records, completed graders, and complete evidence packages.
