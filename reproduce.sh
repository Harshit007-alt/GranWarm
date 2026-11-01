#!/usr/bin/env bash
# One-command reproduction script for GranuWarm
set -e

# Change to script directory
cd "$(dirname "$0")"

# Execute reproduce.py with any passed arguments
python3 reproduce.py "$@"
