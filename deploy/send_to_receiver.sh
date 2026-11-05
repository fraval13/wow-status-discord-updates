#!/usr/bin/env bash
# GitHub runner only: send FILE on stdin to the server's release receiver, then delete FILE.
#
# Usage: deploy/send_to_receiver.sh FILE
# Reads DEPLOY_KEY, KNOWN_HOSTS and DEPLOY_HOST from the environment. The key is the
# dedicated forced-command key (deploy/SERVER.md), so the server runs nothing but the
# receiver, which reads either a release archive or a rollback request from stdin.
set -euo pipefail
umask 077
payload="$1"
key_file="$(mktemp "${RUNNER_TEMP:-/tmp}/wow-character-key.XXXXXX")"
host_file="$(mktemp "${RUNNER_TEMP:-/tmp}/wow-character-known-hosts.XXXXXX")"
trap 'rm -f "$key_file" "$host_file" "$payload"' EXIT
printf '%s\n' "$DEPLOY_KEY" > "$key_file"
printf '%s\n' "$KNOWN_HOSTS" > "$host_file"
# Keepalives: the receiver can wait minutes for a manual homepage publish to finish.
ssh -T -o BatchMode=yes -o ConnectTimeout=20 -o ServerAliveInterval=30 -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile="$host_file" -o IdentitiesOnly=yes -i "$key_file" \
  "wow-character-deploy@$DEPLOY_HOST" < "$payload"
