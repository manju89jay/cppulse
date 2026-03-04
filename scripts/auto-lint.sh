#!/bin/bash
# PostToolUse hook — called automatically after every Write or Edit
# Applies clang-format (C++) or black+ruff (Python) to the modified file

FILE="$1"

if [[ -z "$FILE" ]]; then
  exit 0
fi

# C++ files
if [[ "$FILE" == *.cpp ]] || [[ "$FILE" == *.hpp ]] || [[ "$FILE" == *.h ]]; then
  if command -v clang-format &>/dev/null; then
    clang-format -i "$FILE"
    echo "[auto-lint] clang-format applied: $FILE"
  else
    echo "[auto-lint] WARNING: clang-format not found, skipping"
  fi
fi

# Python files
if [[ "$FILE" == *.py ]]; then
  if command -v black &>/dev/null; then
    black "$FILE" --quiet
    echo "[auto-lint] black applied: $FILE"
  fi
  if command -v ruff &>/dev/null; then
    ruff check "$FILE" --fix --quiet
    echo "[auto-lint] ruff applied: $FILE"
  fi
  if ! command -v black &>/dev/null && ! command -v ruff &>/dev/null; then
    echo "[auto-lint] WARNING: black and ruff not found, skipping"
  fi
fi
