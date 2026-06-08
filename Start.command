#!/usr/bin/env bash
# Double-click this file (macOS) to start AI Income Team. No terminal knowledge needed.
cd "$(dirname "$0")" || exit 1

PY="$(command -v python3 || command -v python)"
if [ -z "$PY" ]; then
  echo "Python 3 isn't installed yet."
  echo "Please install it from https://www.python.org/downloads/ then double-click this again."
  read -r -p "Press Enter to close…" _
  exit 1
fi

"$PY" bootstrap.py
echo
read -r -p "AI Income Team has stopped. Press Enter to close…" _
