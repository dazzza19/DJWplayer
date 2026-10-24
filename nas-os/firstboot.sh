#!/bin/sh
set -eu
if [ ! -e /var/lib/djw/firstboot.done ]; then
  exec /opt/djw-nas-installer/install.sh
fi
exit 0
