#!/bin/zsh
set -eu
project_root="${0:A:h}"
for service in web api worker; do
  case "$service" in
    web) folder="$project_root/songdance/web"; command='pnpm dev --hostname 127.0.0.1' ;;
    api) folder="$project_root/songdance/api"; command='.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000' ;;
    worker) folder="$project_root/songdance/api"; command='.venv/bin/python -m app.worker' ;;
  esac
  launch="cd ${(q)folder} && $command"
  osascript - "$launch" <<'APPLESCRIPT'
on run argv
  tell application "Terminal"
    activate
    do script (item 1 of argv)
  end tell
end run
APPLESCRIPT
done
open 'http://127.0.0.1:3000'
