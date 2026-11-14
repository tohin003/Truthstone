# Truthstone Practices: directory branch

This branch holds one thing: the `truthstone-practices` plugin, at `plugins/truthstone-practices/`, as Claude's plugin directory takes it. It is the folder from `master` without the files that only Codex reads (the Codex manifest, the SVG logos and each skill's `openai.yaml`), built by `scripts/claude_directory_branch.py` on `master`.

Everything else (the Truthstone runtime, the hook plugins, the benchmark and the documentation) is on [`master`](https://github.com/tohin003/Truthstone).
