# Codex CLI Spawn Findings

Date: 2026-09-22

Context: benchmark smoke execution from `Nickshajtan/ai-projects-monorepo` on native Windows, with Codex CLI spawned by the benchmark harness from inside an existing Codex CLI session.

## Working TLS/Auth Setup

The local machine performs HTTPS inspection through Avast Web/Mail Shield. Without its generated root certificate, `codex doctor --json` reported TLS certificate validation failures.

Exported local root CA:

```text
D:\AI\projects\.codex-avast-root.pem
```

Required environment for spawned Codex CLI:

```powershell
$env:CODEX_CA_CERTIFICATE = "D:\AI\projects\.codex-avast-root.pem"
$env:CODEX_API_KEY = $env:OPENAI_API_KEY
```

Notes:

- `CODEX_CA_CERTIFICATE` fixes the TLS trust failure.
- `CODEX_API_KEY=$env:OPENAI_API_KEY` is needed for non-interactive CLI auth in this environment.
- `gpt-5` is accessible here; `gpt-5-codex` returned model-not-found/no-access.

## Executable Resolution

PowerShell resolves:

```text
C:\nvm4w\nodejs\codex.ps1
```

`where.exe codex` reports:

```text
C:\nvm4w\nodejs\codex
C:\nvm4w\nodejs\codex.cmd
```

The benchmark runner should resolve bare `codex` before `subprocess.run(...)`; on Windows the resolved `.cmd` wrapper is the practical executable path for `shell=False`.

## Sandbox Probes

Probe workspace:

```text
D:\AI\projects\.tmp-codex-sandbox-probe
```

### Direct Workspace-Write Request

Command shape:

```powershell
codex exec --model gpt-5 --sandbox workspace-write --skip-git-repo-check "Create OUTPUT.txt"
```

Observed result:

```text
sandbox: read-only
```

The agent refused to write because the effective sandbox remained read-only.

### Config Override

Command shape:

```powershell
codex exec -c 'sandbox_mode="workspace-write"' --model gpt-5 --skip-git-repo-check "Create OUTPUT_CFG.txt"
```

Observed result:

```text
sandbox: read-only
```

The config override did not change the effective sandbox for this nested native Windows invocation.

### Approve-For-Me

Command shape:

```powershell
codex exec --model gpt-5 --approve-for-me --skip-git-repo-check "Create OUTPUT_AUTO.txt"
```

Observed result:

```text
approval: on-request
sandbox: read-only
```

Despite the read-only header, Codex requested/routed approval and successfully wrote the file.

### Danger Full Access

Command shape:

```powershell
codex exec --model gpt-5 --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check "Create OUTPUT_BYPASS.txt"
```

Observed result:

```text
sandbox: danger-full-access
```

The file write succeeded. This is viable only when the benchmark harness already isolates execution in a disposable copied workspace and the operator accepts full local process access.

## Current Recommendation

For a true `workspace-write` Codex CLI smoke on this machine, do not claim success yet: nested native Windows `codex exec` from the current parent Codex CLI session still reports `read-only` even when `--sandbox workspace-write` or `-c sandbox_mode="workspace-write"` is supplied.

For the next benchmark smoke, choose explicitly between:

1. Use `--approve-for-me` as the safest working nested mode found so far. It still reports `read-only`, but it completed a write through approval routing.
2. Use `--dangerously-bypass-approvals-and-sandbox` only as an execution smoke fallback, relying on the benchmark's temporary Git workspace isolation rather than Codex's sandbox.
3. Run the harness from an ordinary PowerShell session outside a parent Codex CLI session and re-test `--sandbox workspace-write`; this may avoid inherited Codex runtime policy.

Do not interpret any smoke result from modes 1 or 2 as evidence that native Windows nested `workspace-write` is functioning.
