# Gemini CLI Spawn Findings

Date: 2026-09-23

Context: benchmark target qualification for `benchmarks/ai-doc-benchmark` on native Windows, from inside an existing Codex CLI session.

## Installed CLI

PowerShell resolves Gemini CLI to:

```text
C:\Users\38098\AppData\Roaming\npm\gemini.ps1
```

The executable used for the benchmark target was the explicit npm command wrapper:

```text
C:\Users\38098\AppData\Roaming\npm\gemini.cmd
```

Observed version:

```text
0.55.1
```

`where.exe gemini` did not resolve the wrapper in this shell, despite the npm wrapper files existing. The target config therefore used the full `.cmd` path instead of relying on PATH lookup.

## Authentication

User settings select API-key auth:

```json
{
  "security": {
    "auth": {
      "selectedType": "gemini-api-key"
    }
  }
}
```

The key is provided by the process environment as `GEMINI_API_KEY`. The key was not persisted into benchmark target config or documentation.

## TLS / CA Handling

Direct network probing to Google's generative API endpoint failed through the local TLS inspection environment. Gemini CLI's bundled troubleshooting documentation recommends `NODE_EXTRA_CA_CERTS` for corporate/private CA roots.

Working CA setting:

```powershell
$env:NODE_EXTRA_CA_CERTS = "D:\AI\projects\.codex-avast-root.pem"
```

The same local Avast root PEM used for Codex was sufficient for Gemini CLI when passed through Node's CA mechanism.

## User Config Isolation

Running Gemini with the normal user home/settings hung in headless mode, even for:

```powershell
gemini --model gemini-2.5-flash --approval-mode yolo --skip-trust --output-format json --prompt "Say READY"
```

Observed behavior:

- process started;
- no output was emitted;
- no file changes were made in the preflight workspace;
- the process required manual interruption.

Using an isolated `GEMINI_CLI_HOME` with minimal settings made headless execution complete:

```json
{
  "security": {
    "auth": {
      "selectedType": "gemini-api-key"
    },
    "toolSandboxing": false
  },
  "hooksConfig": {
    "enabled": false,
    "notifications": false
  },
  "mcpServers": {}
}
```

Working setting:

```powershell
$env:GEMINI_CLI_HOME = "D:\AI\projects\.tmp-gemini-home"
```

This avoids loading user MCP servers and hooks during benchmark execution.

## Model Selection

The first successful smoke probe requested `gemini-2.5-flash`, but the JSON stats reported the effective model as:

```text
gemini-3.5-flash
```

The qualified target therefore uses the exact observed model identifier explicitly:

```text
gemini-3.5-flash
```

## Permission / Approval Behavior

Gemini CLI headless editing worked with:

```text
--approval-mode yolo
--skip-trust
--output-format json
--prompt "Implement task.md"
```

Observed stderr includes:

```text
YOLO mode is enabled. All tool calls will be automatically approved.
```

No interactive human approval was required. Direct preflight verified filesystem mutation by checking the created output file, not by trusting the agent response.

Sandboxing was not enabled with `--sandbox`; the benchmark relies on its disposable copied Git workspace for isolation.

## Qualified Target Shape

Benchmark target command shape:

```text
C:\Users\38098\AppData\Roaming\npm\gemini.cmd --model gemini-3.5-flash --approval-mode yolo --skip-trust --output-format json --prompt "Implement task.md"
```

Target env:

```json
{
  "GEMINI_CLI_HOME": "D:\\AI\\projects\\.tmp-gemini-home",
  "NODE_EXTRA_CA_CERTS": "D:\\AI\\projects\\.codex-avast-root.pem"
}
```

Target config used:

```text
benchmarks/ai-doc-benchmark/runs/smoke-gemini-3.5-flash-yolo-target.json
```

## Qualification Evidence

Direct preflight:

- workspace: `D:\AI\projects\.tmp-gemini-preflight`
- prompt: `Implement task.md`
- result: `gemini-preflight-output.txt` was created with the requested content.

Single benchmark qualification observation:

```text
benchmarks/ai-doc-benchmark/runs/smoke-20260923-gemini-3.5-flash-original-qualification/smoke-20260923-gemini-original-qualification/
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
benchmarks/ai-doc-benchmark/runs/smoke-20260923-gemini-3.5-flash/
```

