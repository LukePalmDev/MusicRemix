#!/bin/zsh
# Launch Ardour 9 on a session (default: Exotica Salsa Remix), logging to bridge/logs/.
# Uses the build compiled from source (~/Builds/ardour-install, no demo limits);
# falls back to the official demo app if the build is missing.
# Usage: launch_ardour.sh [path/to/session.ardour]
ROOT="${0:A:h:h}"
SESSION="${1:-$ROOT/sessions/Exotica Salsa Remix/Exotica Salsa Remix.ardour}"
SRC_BIN="$HOME/Builds/ardour-install/bin/ardour9"
mkdir -p "$ROOT/bridge/logs"
if pgrep -f "lib/ardour9/ardour-9" >/dev/null || pgrep -x Ardour9 >/dev/null; then
  echo "Ardour already running"; exit 0
fi
if [[ -x "$SRC_BIN" ]]; then
  LOG="$ROOT/bridge/logs/ardour-src-$(date +%Y%m%d-%H%M%S).log"
  nohup "$SRC_BIN" "$SESSION" >"$LOG" 2>&1 &
else
  LOG="$ROOT/bridge/logs/ardour-$(date +%Y%m%d-%H%M%S).log"
  open -n --stdout "$LOG" --stderr "$LOG" -a /Applications/Ardour9.app --args "$SESSION"
fi
echo "Launched; log: $LOG"
