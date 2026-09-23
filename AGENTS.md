# Repository Rules

- Keep every hand-maintained source and test file at or below 1000 lines. Split by responsibility before adding code that would exceed the limit.
- `imagegen_plugin/server.cjs` is a generated third-party bundle. Update it from its source project, not by manually splitting or editing the bundle.
- Run `python3 -m unittest discover -q` after changes to Python behavior.
- Token usage comes from local Codex rollout events. Never treat an estimated official-rate cost as a provider invoice or subscription charge.
