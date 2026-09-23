#!/bin/sh
set -eu
case "${TELEPHONY_ENABLED:-false}" in
  true|TRUE|1|yes|YES) ;;
  *) printf '%s\n' 'Experimental Asterisk disabled (TELEPHONY_ENABLED=false).'; exit 0 ;;
esac
export CALLAI_AUDIO_SOCKET_TARGET="${CALLAI_AUDIO_SOCKET_TARGET:-127.0.0.1:9092}"
exec /usr/sbin/asterisk -f -vvv -C /etc/asterisk/asterisk.conf
