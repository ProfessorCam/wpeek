#!/usr/bin/env bash
# Launch wpeek using system Python (needs python3-gi)
cd "$(dirname "$0")"
exec /usr/bin/python3 -m wpeek "$@"
