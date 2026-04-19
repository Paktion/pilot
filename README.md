# Pilot

A macOS menubar agent that drives your iPhone through Apple's iPhone Mirroring window. You describe a task in plain English, Pilot writes a small YAML skill, and then it watches the screen, plans steps with Claude, and synthesizes real taps, swipes, and keystrokes to carry it out. Skills can run on demand, on a schedule, or chain into each other.

Requires macOS 15 (Sequoia) or later, an iPhone paired for iPhone Mirroring, and an Anthropic API key.

## Features

- **Plain-English authoring.** Type "check today's weather" or "text Mom I love you" and Pilot drafts a ready-to-run workflow.
- **Vision-guided execution.** Claude Sonnet reads each screen and picks the next action in a typed observe/act loop.
- **Reliable input.** Synthetic events post through the system HID event tap so iOS treats them as real finger touches.
- **Scheduling.** APScheduler cron expressions plus a launchd agent keep workflows firing across reboots.
- **Chaining.** `on_success.run` lets one workflow feed its captured outputs (totals, IDs, summaries) into another, with null-guards that block chains on missing values.
- **Memory.** SQLite catalogs every skill and run, with a semantic recall layer over local embeddings for questions about prior results.
- **Compiled skills.** After three consecutive green runs, Pilot freezes coordinates and anchors into a compiled plan and skips vision on the hot path.
- **MCP server.** A whitelisted, fail-closed tool surface lets any Claude client list skills, draft new ones, check run status, and trigger runs remotely.
- **Budget guardrails.** Every Claude call is metered against daily and monthly caps with a soft-warn at 80% and a hard-stop at 100%.

## Install

Pilot is two pieces: a Swift menubar app and a Python daemon. Build order:

```bash
git clone https://github.com/Paktion/pilot.git
cd pilot

# 1. Set up the daemon
cd pilotd
python3 -m venv .venv
.venv/bin/pip install -e .
cd ..

# 2. Configure your API key
mkdir -p "$HOME/Library/Application Support/Pilot"
echo "ANTHROPIC_API_KEY=sk-ant-..." > "$HOME/Library/Application Support/Pilot/.env"

# 3. Register the daemon with launchd
cp LaunchAgents/dev.pilot.daemon.plist.template ~/Library/LaunchAgents/dev.pilot.daemon.plist
# edit the plist to point at your .venv/bin/python, then:
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/dev.pilot.daemon.plist

# 4. Build the menubar app
open Pilot.xcodeproj
# In Xcode: select the Pilot scheme and ⌘R
```

Launch Pilot from `/Applications` or Spotlight. The menubar icon is the entry point.

## Usage

1. **Open iPhone Mirroring.** System Settings grants the one-time pairing.
2. **Create a skill.** Click the Pilot menubar icon → Author → describe the task → Save. Pilot drafts a YAML skill and stores it locally.
3. **Run it.** Hit Run in the Library tab, or set a cron schedule.
4. **Inspect.** The Runs tab shows each step's screenshot, the model's reasoning, the final summary, and the Claude API cost.

## Configuration

Settings live in `~/Library/Application Support/Pilot/config.json`. Notable keys:

- `model` — Sonnet tier for vision and planning (default `claude-sonnet-4-6`).
- `model_light` — Haiku tier for cheaper calls like cron parsing.
- `max_daily_budget`, `max_monthly_budget`, `per_task_budget` — dollar caps.
- `use_cgevent` — `true` to dispatch synthetic input through the CGEvent backend (recommended); `false` to fall back to pyautogui.

## License

MIT. See `LICENSE`.
