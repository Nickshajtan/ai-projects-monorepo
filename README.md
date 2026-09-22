# ai-tools

`ai-tools` is an umbrella workspace for AI tooling projects and their benchmark
projects.

## Layout

```text
projects/
  ai-doc/                    # system under test for ai-doc benchmarks
  ai-spec-oriented-setup/     # specification-oriented tooling project

benchmarks/
  ai-doc-benchmark/           # benchmark project for projects/ai-doc

ai-doc-benchmark-definition-v0.1.md
```

`projects/ai-doc` and `projects/ai-spec-oriented-setup` are Git submodules. Benchmark
projects live under `benchmarks/` so additional benchmark projects can be added without
mixing benchmark code into the systems under test.

## Bootstrap

After cloning this repository, install the workspace hooks and submodules:

```bash
npm install
```

This installs Husky hooks and runs `scripts/install-gitmodules.mjs`, which synchronizes
`.gitmodules`, initializes missing submodules, and updates them to the commits recorded
by this repository.

If you do not want to use npm, run the submodule installer directly:

```bash
node scripts/install-gitmodules.mjs
```

Git Bash users can also run `sh scripts/install-gitmodules.sh`; it delegates to the
Node installer.

Git does not execute repository scripts automatically on clone. The Husky hooks become
active after `npm install` and keep submodules synchronized after checkout, merge, and
history rewrite operations.

## Validation

Validate the current `ai-doc` benchmark definition layer with:

```powershell
$env:PYTHONPATH = "src"
..\..\projects\ai-doc\.venv\Scripts\python.exe -m ai_doc_benchmarks validate corpus\benchmark-corpus-v0.1.json
..\..\projects\ai-doc\.venv\Scripts\python.exe -m unittest discover -s tests
```

Run those commands from `benchmarks/ai-doc-benchmark`.
