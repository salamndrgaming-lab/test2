#!/usr/bin/env bash
# Start AI Income Team on Linux. Double-click (if your file manager allows running
# scripts) or run:  ./start.sh
cd "$(dirname "$0")" || exit 1

PY="$(command -v python3 || command -v python)"
if [ -z "$PY" ]; then
  echo "Python 3 isn't installed yet."
  echo "Install it with your package manager (e.g. 'sudo apt install python3 python3-venv')"
  echo "or from https://www.python.org/downloads/ , then run this again."
  read -r -p "Press Enter to close…" _
  exit 1
fi

"$PY" bootstrap.py
echo
read -r -p "AI Income Team has stopped. Press Enter to close…" _
