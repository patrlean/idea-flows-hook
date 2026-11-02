# Idea Flows Hook

Keep an idea board up to date from the Codex chats where the work happens.

[简体中文](README.zh-CN.md) · [Tests](https://github.com/patrlean/idea-flows-hook/actions/workflows/test.yml) · MIT

Idea Flows asks the active Codex agent to record a short, evidence-based progress update for projects you explicitly enroll. A Stop hook saves it locally and can POST it to your own dashboard. There is no separate model service or API key.

```text
Enrolled Codex chat → factual summary → local event store → optional webhook → your dashboard
```

## Status rules

| Status | Meaning | Required evidence for a change |
| --- | --- | --- |
| `idea` | Planning | The current conversation |
| `research` | Active investigation before implementation | Observed research activity, findings, and open questions |
| `dev` | Implementation in progress | Actual work or a user-directed change |
| `live` | Deployed | Successful deployment, a verified URL, and observed evidence |
| `discarded` | Archived / abandoned | An explicit archival instruction quoted from the current user turn |

Inactivity never archives a project. Routine discussion should preserve its status. The agent supplies the facts: the script validates required fields and exact quotes, but cannot independently prove a deployment succeeded. Review summaries when correctness matters.

Literature reviews, competitor analysis, requirements discovery, and feasibility checks use `research` until implementation starts. Record the findings and what remains to be verified, with non-empty evidence. Finishing a research report does not make a project `live`; occasional research on an existing `dev` or `live` project does not move it backward automatically. Webhook receivers must accept all five status values. Existing local databases need no migration.

## Install in Codex

Requires **Python 3.9+** available as `python3`, and a Codex desktop/CLI version with native plugin hooks. Bundled hook commands target macOS and Linux. The Python core is also tested on Windows; Windows hook command wiring is not provided in this release.

```sh
codex plugin marketplace add patrlean/idea-flows-hook
```

Open the Plugins Directory, select **Idea Flows Tools** (`idea-flows-tools`), and install **Idea Flows** (`idea-flows`). Restart the desktop app if the source does not appear. Use the plugin's **Set up** action to enroll a directory. Review and trust its commands through Codex's `/hooks` interface, then start a new turn in that directory to verify activation.

This is a manually installed plugin from a Git marketplace, not a listing in the universal plugin directory. See the [official packaging and hooks documentation](https://developers.openai.com/plugins/build/plugins).

Do not install a duplicate set of global hooks alongside the plugin.

Updating from 0.1.x: refresh the source with `codex plugin marketplace upgrade idea-flows-tools`, then update Idea Flows in the Plugins Directory. The hook commands and config paths stay the same. If you use a custom receiver, add `research` to its accepted statuses before sending research events.

The plugin is named **Idea Flows**. `patrlean` in the install command is the GitHub repository owner, not part of the plugin name. Your own name is not required in the plugin name. Each installer configures their own local project list and optional webhook.

## Configure manually

Clone this repository if you want to inspect or configure the hook directly:

```sh
git clone https://github.com/patrlean/idea-flows-hook.git
cd idea-flows-hook
python3 scripts/idea_flows.py init
python3 scripts/idea_flows.py enroll --id my-project --name 'My project' --cwd /absolute/path/to/project
```

`init` prints the configuration path. It does not overwrite an existing configuration. Enrollment covers that directory and its descendants; the closest enrolled parent wins. It does not scan chats or enroll other directories. Remove an entry from `projects` in the config to stop tracking it.

The default config is `~/.config/idea-flows/config.json` (`XDG_CONFIG_HOME` is respected). Data uses Codex's `PLUGIN_DATA` when available, otherwise `~/.local/share/idea-flows`. Override these with `IDEA_FLOWS_CONFIG` / `IDEA_FLOWS_DATA_DIR`, or `--config` / `--data-dir` **before** the subcommand. Hooks pass the resolved paths to the agent's recording command so different execution environments use the same store.

```sh
python3 scripts/idea_flows.py --data-dir /path/printed/by/plugin status
python3 scripts/idea_flows.py --data-dir /path/printed/by/plugin flush
```

The active turn's injected recording command includes the actual data directory. Use that path for inspection when installed as a plugin.

### Send updates to a dashboard

Local recording works without a server. To enable delivery, add `webhook` to the config printed by `init`; see [the example](examples/config.example.json):

```json
"webhook": {
  "url": "https://your-dashboard.example/api/sync",
  "headers_env": {"Authorization": "IDEA_FLOWS_AUTHORIZATION"}
}
```

Set `IDEA_FLOWS_AUTHORIZATION` in the environment of the Codex process, including any `Bearer ` prefix required by your receiver. Launching the desktop app normally may not inherit terminal exports. The config stores environment variable **names**, never credential values. Other headers can be mapped in the same way. Restart Codex after changing its launch environment.

Delivery uses HTTPS (HTTP is allowed only for loopback testing), does not follow redirects, and accepts any 2xx response. Failed events remain in SQLite and retry on later enrolled Stop events or `flush`. Each invocation attempts up to three events. Delivery is **at least once**: your receiver must deduplicate by `eventId`. A response can be lost after the server accepts a request.

Local-only events are retained. Enabling a webhook later delivers that backlog too; inspect or remove your local store first if you do not want historical summaries sent.

### Event contract

A POST body contains these fields:

```json
{
  "id": "my-project",
  "eventId": "sha256-of-session-and-turn",
  "observedAt": "2026-01-01T12:00:00+00:00",
  "threadId": "codex-session-id",
  "status": "dev",
  "progress": "Implemented project status editing.",
  "evidence": "Updated the card interaction and checked it in the browser.",
  "deploymentVerified": false,
  "deploymentUrl": "",
  "archiveConfirmed": false,
  "statusConfirmed": false
}
```

`threadId` is a local chat identifier, not a universally portable web URL. The receiver should map it to a supported Codex deep link if it needs navigation. Preserve manually chosen dashboard states unless an incoming event has new deployment evidence or a confirmed user instruction; use `observedAt` to ignore older state updates.

This repository contains the hook and event contract. Bring your own receiver/dashboard; no hosted site, dashboard UI, database account, or authentication service is included.

## Behavior and privacy

- Only enrolled directory trees are tracked. All chats in an enrolled directory qualify; per-chat filtering is not implemented.
- The current user prompt is temporarily stored locally for quote validation, then deleted from the active context table when Stop finishes. Interrupted turns can leave context rows. SQLite may retain deleted bytes in free pages; this is not secure erasure. Remove the local database if you need to clear its history.
- Persistent events include project IDs, chat IDs, timestamps, summaries, and evidence. The agent is instructed to exclude secrets and personal details, but generated summaries should still be reviewed before connecting a public receiver.
- By default, a missing record makes Stop ask the agent to continue **once**. This may consume additional Codex capacity. Set `"require_record": false` to skip that continuation.
- Local state updates are transactional and events are deduplicated. A late Stop from an older turn does not replace newer local state. Webhook receivers must apply equivalent checks.
- Hooks fail softly: configuration/delivery issues produce a short system message. `flush` exits nonzero on delivery/configuration errors without printing secret header values.

Uninstall through Codex's plugin UI. Config and history remain in the paths above; delete them separately if desired. Hook trust is always managed by Codex, not this script.

## Development

```sh
python3 -m unittest discover -s tests -v
```

Tests cover enrollment boundaries, nested projects, quoting paths with spaces, status evidence, one-time continuations, concurrent turns, idempotency, local retention, webhook retries, credential handling, and redirect refusal. CI runs Python 3.9 and 3.13 on Linux, macOS, and Windows. These direct tests do not establish native hook activation in a particular Codex installation; verify that separately after installation.
