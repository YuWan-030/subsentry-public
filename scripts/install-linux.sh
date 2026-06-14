#!/usr/bin/env bash
set -Eeuo pipefail

APP_NAME="subsentry"
SERVICE_NAME="subsentry"
DEFAULT_INSTALL_DIR="${SUBSENTRY_DEFAULT_INSTALL_DIR:-/opt/subsentry}"
DEFAULT_BACKEND_PORT="${SUBSENTRY_BACKEND_PORT:-4398}"
DEFAULT_HTTP_PORT="${SUBSENTRY_HTTP_PORT:-8080}"
DEFAULT_DB_TYPE="${SUBSENTRY_INSTALL_DB_TYPE:-sqlite}"
DEFAULT_RUN_USER="${SUBSENTRY_RUN_USER:-$APP_NAME}"
DEFAULT_REPO_URL="${SUBSENTRY_REPO_URL:-https://github.com/YuWan-030/subsentry-public.git}"
DEFAULT_ARCHIVE_URL="${SUBSENTRY_ARCHIVE_URL:-https://github.com/YuWan-030/subsentry-public/archive/refs/heads/main.tar.gz}"
INSTALL_NGINX="${SUBSENTRY_INSTALL_NGINX:-true}"
ASSUME_YES="${SUBSENTRY_ASSUME_YES:-false}"

TTY="/dev/tty"

log() {
  printf '\033[1;34m[SubSentry]\033[0m %s\n' "$*"
}

warn() {
  printf '\033[1;33m[SubSentry]\033[0m %s\n' "$*"
}

success() {
  printf '\033[1;32m[SubSentry]\033[0m %s\n' "$*"
}

die() {
  printf '\033[1;31m[SubSentry]\033[0m %s\n' "$*" >&2
  exit 1
}

prompt() {
  local label="$1"
  local default_value="$2"
  local value=""
  if [[ "$ASSUME_YES" == "true" ]]; then
    printf '%s' "$default_value"
    return
  fi
  if [[ -r "$TTY" ]]; then
    read -r -p "$label [$default_value]: " value < "$TTY" || true
  fi
  printf '%s' "${value:-$default_value}"
}

require_linux() {
  [[ "$(uname -s)" == "Linux" ]] || die "This installer only supports Linux."
  command -v systemctl >/dev/null 2>&1 || die "systemd is required."
}

setup_sudo() {
  if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    SUDO=""
  elif command -v sudo >/dev/null 2>&1; then
    SUDO="sudo"
  else
    die "Please run as root or install sudo first."
  fi
}

detect_pkg_manager() {
  if command -v apt-get >/dev/null 2>&1; then
    PKG_MANAGER="apt"
  elif command -v dnf >/dev/null 2>&1; then
    PKG_MANAGER="dnf"
  elif command -v yum >/dev/null 2>&1; then
    PKG_MANAGER="yum"
  else
    die "Unsupported Linux distribution. Please use Debian/Ubuntu, Fedora, CentOS, Rocky, or AlmaLinux."
  fi
}

port_in_use() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -ltn "( sport = :$port )" 2>/dev/null | awk 'NR > 1 { found = 1 } END { exit found ? 0 : 1 }'
    return
  fi
  if command -v lsof >/dev/null 2>&1; then
    lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
    return
  fi
  return 1
}

next_available_port() {
  local port="$1"
  while port_in_use "$port"; do
    port=$((port + 1))
  done
  printf '%s' "$port"
}

normalize_port() {
  local label="$1"
  local requested="$2"
  local resolved
  [[ "$requested" =~ ^[0-9]+$ ]] || die "$label must be a number."
  [[ "$requested" -ge 1 && "$requested" -le 65535 ]] || die "$label must be between 1 and 65535."
  resolved="$(next_available_port "$requested")"
  if [[ "$resolved" != "$requested" ]]; then
    warn "$label $requested is already in use. Using $resolved instead."
  fi
  printf '%s' "$resolved"
}

install_base_packages() {
  local packages
  log "Installing system dependencies..."
  case "$PKG_MANAGER" in
    apt)
      $SUDO apt-get update
      packages="ca-certificates curl git openssl python3 python3-pip python3-venv rsync tar"
      if [[ "$INSTALL_NGINX" == "true" ]]; then
        packages="$packages nginx"
      fi
      $SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y $packages
      ;;
    dnf)
      packages="ca-certificates curl git openssl python3 python3-pip rsync tar"
      if [[ "$INSTALL_NGINX" == "true" ]]; then
        packages="$packages nginx"
      fi
      $SUDO dnf install -y $packages
      ;;
    yum)
      packages="ca-certificates curl git openssl python3 python3-pip rsync tar"
      if [[ "$INSTALL_NGINX" == "true" ]]; then
        packages="$packages nginx"
      fi
      $SUDO yum install -y $packages
      ;;
  esac
}

node_major_version() {
  node -v 2>/dev/null | sed -E 's/^v([0-9]+).*/\1/' || true
}

install_nodejs() {
  local major
  major="$(node_major_version)"
  if [[ -n "$major" && "$major" -ge 20 ]]; then
    log "Node.js $(node -v) detected."
    return
  fi

  log "Installing Node.js 22..."
  case "$PKG_MANAGER" in
    apt)
      curl -fsSL https://deb.nodesource.com/setup_22.x | $SUDO bash -
      $SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y nodejs
      ;;
    dnf)
      curl -fsSL https://rpm.nodesource.com/setup_22.x | $SUDO bash -
      $SUDO dnf install -y nodejs
      ;;
    yum)
      curl -fsSL https://rpm.nodesource.com/setup_22.x | $SUDO bash -
      $SUDO yum install -y nodejs
      ;;
  esac
}

ensure_user() {
  if id "$RUN_USER" >/dev/null 2>&1; then
    log "Runtime user $RUN_USER already exists."
    return
  fi
  log "Creating runtime user $RUN_USER..."
  $SUDO useradd --system --home "$INSTALL_DIR" --shell /usr/sbin/nologin "$RUN_USER"
}

prepare_source() {
  local current_dir
  current_dir="$(pwd)"
  if [[ -f "$current_dir/backend/app/main.py" && -f "$current_dir/frontend/package.json" ]]; then
    SOURCE_DIR="$current_dir"
    log "Using current repository: $SOURCE_DIR"
    return
  fi

  SOURCE_DIR="$(mktemp -d)"
  log "Cloning $REPO_URL..."
  for attempt in 1 2 3; do
    if git -c http.version=HTTP/1.1 clone --depth 1 "$REPO_URL" "$SOURCE_DIR"; then
      return
    fi
    warn "Clone failed, retrying ($attempt/3)..."
    rm -rf "$SOURCE_DIR"
    SOURCE_DIR="$(mktemp -d)"
    sleep 3
  done

  warn "Git clone failed. Falling back to source archive download..."
  local archive_file
  archive_file="$(mktemp)"
  for attempt in 1 2 3; do
    if curl -fL --retry 3 --retry-delay 2 "$DEFAULT_ARCHIVE_URL" -o "$archive_file"; then
      tar -xzf "$archive_file" --strip-components=1 -C "$SOURCE_DIR"
      rm -f "$archive_file"
      return
    fi
    warn "Archive download failed, retrying ($attempt/3)..."
    sleep 3
  done
  rm -f "$archive_file"
  die "Failed to download source from $REPO_URL or $DEFAULT_ARCHIVE_URL"
}

sync_app_files() {
  log "Copying application files to $APP_DIR..."
  $SUDO mkdir -p "$APP_DIR" "$DATA_DIR" "$INSTALL_DIR/backups"
  if [[ -d "$APP_DIR/backend" || -d "$APP_DIR/frontend" ]]; then
    local backup_dir
    backup_dir="$INSTALL_DIR/backups/app-$(date +%Y%m%d-%H%M%S)"
    $SUDO mkdir -p "$backup_dir"
    $SUDO rsync -a --delete \
      --exclude '.venv' \
      --exclude 'node_modules' \
      --exclude 'frontend/node_modules' \
      --exclude 'frontend/dist' \
      "$APP_DIR/" "$backup_dir/"
    warn "Existing app backup saved to $backup_dir"
  fi

  $SUDO rsync -a --delete \
    --exclude '.git' \
    --exclude '.idea' \
    --exclude '.venv' \
    --exclude '__pycache__' \
    --exclude 'node_modules' \
    --exclude 'frontend/node_modules' \
    --exclude 'frontend/dist' \
    --exclude '*.db' \
    --exclude '.env' \
    "$SOURCE_DIR/" "$APP_DIR/"
}

random_hex() {
  openssl rand -hex 32
}

write_env_file() {
  local env_file="$APP_DIR/.env"
  if [[ -f "$env_file" ]]; then
    warn "Keeping existing .env: $env_file"
    return
  fi

  log "Writing default .env..."
  $SUDO tee "$env_file" >/dev/null <<EOF
SUBSENTRY_DB_TYPE=$DB_TYPE
SUBSENTRY_SQLITE_FILE=$DATA_DIR/subsentry.db
SUBSENTRY_SECRET_KEY=$(random_hex)
SUBSENTRY_CRON_TOKEN=$(random_hex)
SUBSENTRY_CORS_ORIGINS=*
SUBSENTRY_PUBLIC_SUBSCRIPTION_BASE_URL=$PUBLIC_URL
SUBSENTRY_NODE_PROBE_ENABLED=true
SUBSENTRY_NODE_PROBE_INTERVAL_SECONDS=300
EOF
}

install_python_deps() {
  log "Installing Python dependencies..."
  $SUDO python3 -m venv "$APP_DIR/.venv"
  $SUDO "$APP_DIR/.venv/bin/python" -m pip install --upgrade pip wheel
  $SUDO "$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/backend/requirements.txt"
}

build_frontend() {
  log "Building frontend..."
  (
    cd "$APP_DIR/frontend"
    $SUDO npm install
    $SUDO npm run build
  )
}

write_systemd_service() {
  log "Writing systemd service..."
  $SUDO tee "/etc/systemd/system/$SERVICE_NAME.service" >/dev/null <<EOF
[Unit]
Description=SubSentry panel
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$RUN_USER
Group=$RUN_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/.venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port $BACKEND_PORT
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
}

write_nginx_site() {
  log "Writing Nginx site..."
  $SUDO tee "/etc/nginx/conf.d/$APP_NAME.conf" >/dev/null <<EOF
server {
    listen $HTTP_PORT;
    server_name _;

    root $APP_DIR/frontend/dist;
    index index.html;

    client_max_body_size 20m;

    error_page 500 502 503 504 /index.html;

    location /api/ {
        proxy_pass http://127.0.0.1:$BACKEND_PORT;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location / {
        try_files \$uri \$uri/ /index.html;
    }
}
EOF

  if [[ -f /etc/nginx/sites-enabled/default ]]; then
    $SUDO rm -f /etc/nginx/sites-enabled/default
  fi
  $SUDO nginx -t
}

fix_permissions() {
  log "Fixing permissions..."
  $SUDO chown -R "$RUN_USER:$RUN_USER" "$INSTALL_DIR"
  $SUDO chmod 755 "$INSTALL_DIR" "$APP_DIR" "$APP_DIR/frontend" "$APP_DIR/frontend/dist"
  $SUDO chmod 640 "$APP_DIR/.env"
  $SUDO chmod 750 "$DATA_DIR"
}

start_services() {
  log "Starting services..."
  $SUDO systemctl daemon-reload
  $SUDO systemctl enable --now "$SERVICE_NAME"
  if [[ "$INSTALL_NGINX" == "true" ]]; then
    $SUDO systemctl enable --now nginx
    $SUDO systemctl restart nginx
  fi
}

print_summary() {
  if [[ "$INSTALL_NGINX" == "true" ]]; then
    cat <<EOF

SubSentry has been installed.

Install path: $APP_DIR
Data path: $DATA_DIR
Service: systemctl status $SERVICE_NAME
Logs: journalctl -u $SERVICE_NAME -f

EOF
    success "Panel URL: $PUBLIC_URL"
    success "First-run installer: $PUBLIC_URL/install"
    printf '\n'
  else
    cat <<EOF

SubSentry backend has been installed for aaPanel/BT Panel.

Install path: $APP_DIR
Data path: $DATA_DIR
Service: systemctl status $SERVICE_NAME
Logs: journalctl -u $SERVICE_NAME -f

In aaPanel/BT Panel:
1. Add a website and set its document root to: $APP_DIR/frontend/dist
2. Add reverse proxy /api/ to: http://127.0.0.1:$BACKEND_PORT
3. Visit your site and open /install to finish the first-run installer.

EOF
    success "Backend URL: http://127.0.0.1:$BACKEND_PORT"
    success "Frontend root: $APP_DIR/frontend/dist"
    success "After configuring aaPanel/BT Panel, open: http://your-domain/install"
    printf '\n'
  fi
}

default_public_url() {
  local server_ip="$1"
  local http_port="$2"
  local host="${server_ip:-127.0.0.1}"
  if [[ "$INSTALL_NGINX" == "true" && "$http_port" != "80" ]]; then
    printf 'http://%s:%s' "$host" "$http_port"
  elif [[ "$INSTALL_NGINX" == "true" ]]; then
    printf 'http://%s' "$host"
  else
    printf 'http://%s' "$host"
  fi
}

main() {
  require_linux
  setup_sudo
  detect_pkg_manager

  INSTALL_DIR="$(prompt 'Install directory' "$DEFAULT_INSTALL_DIR")"
  APP_DIR="$INSTALL_DIR/app"
  DATA_DIR="$INSTALL_DIR/data"
  BACKEND_PORT="$(prompt 'Backend port' "$DEFAULT_BACKEND_PORT")"
  BACKEND_PORT="$(normalize_port 'Backend port' "$BACKEND_PORT")"
  if [[ "$INSTALL_NGINX" == "true" ]]; then
    HTTP_PORT="$(prompt 'Public HTTP port' "$DEFAULT_HTTP_PORT")"
    HTTP_PORT="$(normalize_port 'Public HTTP port' "$HTTP_PORT")"
  else
    HTTP_PORT=""
  fi
  DB_TYPE="$(prompt 'Database type' "$DEFAULT_DB_TYPE")"
  RUN_USER="$(prompt 'Runtime user' "$DEFAULT_RUN_USER")"
  REPO_URL="$DEFAULT_REPO_URL"
  SERVER_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
  PUBLIC_URL="$(prompt 'Public site URL' "$(default_public_url "$SERVER_IP" "${HTTP_PORT:-80}")")"

  [[ "$DB_TYPE" == "sqlite" ]] || die "The one-click installer defaults to SQLite. Use the web installer after startup to switch to MySQL."

  install_base_packages
  install_nodejs
  ensure_user
  prepare_source
  sync_app_files
  write_env_file
  install_python_deps
  build_frontend
  write_systemd_service
  if [[ "$INSTALL_NGINX" == "true" ]]; then
    write_nginx_site
  fi
  fix_permissions
  start_services
  print_summary
}

main "$@"
