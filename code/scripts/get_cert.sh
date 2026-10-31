#!/usr/bin/env bash
# Get (or renew) a Let's Encrypt certificate for this site, for the voice relay (TURN over TLS).
# Phones on mobile networks and Wi-Fi can't reach the voice media ports directly (the team
# server lets no UDP through); TURN over TLS on a TCP port gets their audio through. The HTTP
# challenge is answered by the assistant itself (/.well-known/acme-challenge, served from
# data/acme), so nothing else on the server is needed. Run from code/:
#   scripts/get_cert.sh web4.mendes.dev
# Then set LIVEKIT_TURN_DOMAIN, LIVEKIT_TURN_CERT and LIVEKIT_TURN_KEY in .env (see .env.example).
set -euo pipefail
domain="${1:?usage: scripts/get_cert.sh <domain>}"
state="${CERT_DIR:-$HOME/.local/certbot}"
mkdir -p data/acme "$state"
~/.local/bin/uv run -q --with certbot certbot certonly --non-interactive --agree-tos \
  --register-unsafely-without-email --webroot -w data/acme -d "$domain" \
  --config-dir "$state" --work-dir "$state/work" --logs-dir "$state/logs" --keep-until-expiring
echo "cert: $state/live/$domain/fullchain.pem"
echo "key:  $state/live/$domain/privkey.pem"
