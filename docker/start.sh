#!/bin/bash
# Run API + nginx; if either exits, stop the other so the container exits (and restarts).
set -uo pipefail

python -m app &   # binds 127.0.0.1:$PORT - only reachable through nginx
api=$!
nginx -g 'daemon off;' &
web=$!

trap 'kill -TERM "$api" "$web" 2>/dev/null' TERM INT
wait -n "$api" "$web"
code=$?
kill -TERM "$api" "$web" 2>/dev/null
wait
exit "$code"
