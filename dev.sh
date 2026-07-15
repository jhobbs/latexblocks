#!/bin/sh
# Run a command in the latexblocks dev container. Runs as the host user so
# files written into the mounted repo (node_modules, build outputs) are not
# root-owned; HOME=/tmp keeps npm's cache writable for that user.
exec docker run --rm -i -v "$(pwd)":/app -w /app \
  -u "$(id -u):$(id -g)" -e HOME=/tmp \
  latexblocks-dev "$@"
