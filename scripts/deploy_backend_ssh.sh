#!/bin/sh
# Root-owned forced command; accepts no interactive shell, forwarding or SFTP.
set -eu
exec sudo -n /usr/local/sbin/aeroblade-deploy "${SSH_ORIGINAL_COMMAND:-}"
