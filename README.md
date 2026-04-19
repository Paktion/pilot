# Pilot

Native macOS menubar app that records, schedules, and replays iPhone workflows
through iPhone Mirroring + Claude. Exposes an MCP server so Claude Code can
drive the phone too.

Requires macOS 15 (Sequoia) or later and a paired iPhone.

## Status

Hackathon build. The authoring surface, scheduler, MCP, and session recorder
all work end-to-end. Expect rough edges on the agent-loop.

## Install (dev)

```bash
# One-time
xcodegen generate
pip install -e pilotd --upgrade
cp .env.example .env  # paste your ANTHROPIC_API_KEY

# Run
python -m pilot                     # start the daemon
open Pilot.xcodeproj                # build + run the SwiftUI app
claude mcp add pilot --scope user \
  --transport stdio -- \
  $(pwd)/pilotd/.venv/bin/python -m pilot.mcp
```

## License

MIT. See `LICENSE`.
