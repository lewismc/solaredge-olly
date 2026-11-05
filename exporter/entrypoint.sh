#!/bin/sh
# The log directory is a shared volume, so the image's ownership does not apply
# to it. Create it as root, then drop to the exporter user.
mkdir -p /var/log/solaredge
chown solaredge:solaredge /var/log/solaredge
exec su-exec solaredge "$@"
