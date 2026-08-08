#!/usr/bin/env bash
# Run on a fresh Oracle Always Free Ubuntu/Oracle Linux ARM VM as a sudo-capable user.
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/patrickcabel/d2buildbot/main/deploy/oracle/setup.sh | bash
# Or clone the repo and:  bash deploy/oracle/setup.sh
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/patrickcabel/d2buildbot.git}"
APP_DIR="${APP_DIR:-$HOME/d2buildbot}"

echo "==> Installing Docker…"
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER" || true
fi

# docker compose plugin
if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose plugin missing — install docker-compose-plugin via your package manager."
  exit 1
fi

echo "==> Cloning / updating repo in $APP_DIR…"
if [[ -d "$APP_DIR/.git" ]]; then
  git -C "$APP_DIR" pull --ff-only
else
  git clone "$REPO_URL" "$APP_DIR"
fi

cd "$APP_DIR/deploy/oracle"

if [[ ! -f .env ]]; then
  cp .env.example .env
  # Guess public IP for sslip.io
  IP="$(curl -4 -fsSL https://ifconfig.me 2>/dev/null || curl -4 -fsSL https://icanhazip.com || true)"
  IP="$(echo "$IP" | tr -d '[:space:]')"
  if [[ -n "$IP" ]]; then
    SSLIP="$(echo "$IP" | tr '.' '-').sslip.io"
    # portable sed
    if sed --version >/dev/null 2>&1; then
      sed -i "s|YOUR-IP-WITH-DASHES.sslip.io|$SSLIP|g" .env
    else
      sed -i '' "s|YOUR-IP-WITH-DASHES.sslip.io|$SSLIP|g" .env
    fi
    echo "==> Detected public IP $IP → DOMAIN=$SSLIP"
  fi
  # Generate Fernet key if python3 + cryptography available; else leave blank (app can derive).
  if command -v python3 >/dev/null 2>&1; then
    KEY="$(python3 - <<'PY' 2>/dev/null || true
try:
    from cryptography.fernet import Fernet
    print(Fernet.generate_key().decode())
except Exception:
    pass
PY
)"
    if [[ -n "${KEY:-}" ]]; then
      if grep -q '^TOKEN_ENCRYPTION_KEY=$' .env; then
        if sed --version >/dev/null 2>&1; then
          sed -i "s|^TOKEN_ENCRYPTION_KEY=$|TOKEN_ENCRYPTION_KEY=$KEY|" .env
        else
          sed -i '' "s|^TOKEN_ENCRYPTION_KEY=$|TOKEN_ENCRYPTION_KEY=$KEY|" .env
        fi
      fi
    fi
  fi
  echo
  echo "Edit deploy/oracle/.env and add your Bungie API credentials:"
  echo "  nano $APP_DIR/deploy/oracle/.env"
  echo
  echo "Then run:"
  echo "  cd $APP_DIR/deploy/oracle && docker compose up -d --build"
  echo
  echo "Also open TCP 80 and 443 in the Oracle VCN Security List / NSG."
  exit 0
fi

echo "==> Building and starting (this takes several minutes on first build)…"
docker compose up -d --build

echo
echo "Done. Check:"
echo "  docker compose ps"
echo "  curl -fsS https://\$(grep PUBLIC_BASE_URL .env | cut -d= -f2- | tr -d '[:space:]' | sed 's|https://||')/api/health || true"
echo
echo "Set Bungie Redirect URL to:"
grep PUBLIC_BASE_URL .env | sed 's|.*=||' | awk '{print $1 "/api/auth/callback"}'
