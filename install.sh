#!/bin/bash
# Debian/Ubuntu: Systemvoraussetzungen und genau einen Python-Dienst installieren.
set -euo pipefail
cd -- "$(dirname -- "$0")"
if [ "$(id -u)" -ne 0 ]; then
  exec sudo -- "$PWD/install.sh" "$@"
fi
. /etc/os-release
case "${ID:-} ${ID_LIKE:-}" in
  *debian*|*ubuntu*) ;;
  *) echo 'Unterstützt werden Debian und Ubuntu.' >&2; exit 1 ;;
esac
apt-get update
apt-get install -y python3 python3-venv git libglib2.0-0
python3 -c 'import sys; assert sys.version_info >= (3, 11), "Python >= 3.11 erforderlich"'
python3 -m biathlon_target_vision.deployment --source "$PWD"
