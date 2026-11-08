#!/usr/bin/env bash
# The one command we run:  ./run.sh <input_dir> <output.json>
# Change what it calls, not how it is called. It must finish in 30 minutes.
# Standard library only: nothing to install. PYTHON=... overrides the interpreter (default python3).
set -euo pipefail
if [ "$#" -ne 2 ]; then
  echo "usage: ./run.sh <input_dir> <output.json>" >&2
  exit 2
fi
"${PYTHON:-python3}" "$(dirname "$0")/solution.py" "$1" "$2"
