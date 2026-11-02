---
name: setup
description: Set up Idea Flows project tracking when the user installs this plugin or asks to enroll, inspect, or configure project progress sync.
---

Locate this plugin's `scripts/idea_flows.py` relative to this skill, two directories up. Quote paths in shell commands.

1. Run `python3 <script> init` to create an empty configuration without replacing existing settings. Read the printed config path.
2. Use only project directories the user explicitly selected. If none were specified, ask which directory to track; never scan or enroll all chats. Run `python3 <script> enroll --id <stable-id> --name <name> --cwd <absolute-directory>` for each selected directory.
3. Default to local recording. Configure a webhook only when requested, using README.md and `examples/config.example.json`. Store credential environment variable names in config, never their values. Never copy prompts, auth files, or personal project configs into this repository.
4. Explain that the user must review and trust the hook in Codex's `/hooks` UI; do not modify trust records. Plugin hooks are bundled: do not also install a second set of global hooks. Native hook activation must be verified in a subsequent enrolled chat, not claimed from a direct script test.
5. Report config location and enrolled projects. The current agent creates the summary; no extra model API key is needed. Missing records can trigger one Stop continuation and use additional Codex capacity; setting `require_record` to false disables that continuation.

State rules: `idea` is an idea or planning; `research` is active literature, competitor, requirements, or feasibility investigation before implementation; `dev` means actual implementation has started. Research summaries should record findings, open questions, and observed evidence. A completed research report is not a launch. Preserve status unless this turn provides evidence; occasional research must not move an existing dev/live project back to research. `live` needs actual successful deployment and URL verification, not a local build or preview. `discarded` needs the user's explicit archival instruction. Never infer archival from inactivity. For correctness and privacy, summarize only project progress and redact sensitive content.
