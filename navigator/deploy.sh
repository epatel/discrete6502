#!/bin/sh
# Deploy the board navigator to ai.memention.net/d6502navigator.
#
#   navigator/deploy.sh            # sync code + data, restart the service
#
# The two board renders and the prebuilt part index are shipped as artifacts:
# the server needs no KiCad, no PIL and no numpy, only python3 stdlib.  Rebuild
# board.json locally with build_data.py after any placement change, then re-run
# this.  The write token lives only on the server (/etc/d6502navigator.env).
set -e
HOST=${HOST:-ai}
DEST=/home/epatel/vps-ai/projects/d6502navigator
HERE=$(cd "$(dirname "$0")" && pwd)

test -f "$HERE/data/board.json" || { echo "no data/board.json — run build_data.py first"; exit 1; }

echo "→ syncing to $HOST:$DEST"
ssh "$HOST" "mkdir -p $DEST/static $DEST/data $DEST/gen"
rsync -az --delete "$HERE/static/" "$HOST:$DEST/static/"
rsync -az "$HERE/server.py" "$HERE/groups.py" "$HERE/navctl.py" "$HERE/README.md" "$HOST:$DEST/"
rsync -az "$HERE/data/board.json" "$HOST:$DEST/data/"
rsync -az "$HERE/../gen/board_top.png" "$HERE/../gen/board_bottom.png" "$HOST:$DEST/gen/"

echo "→ restarting"
ssh "$HOST" "sudo systemctl restart d6502navigator && sleep 1 && systemctl is-active d6502navigator"
echo "→ https://ai.memention.net/d6502navigator/"
