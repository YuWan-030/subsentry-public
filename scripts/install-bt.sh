#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_URL="${SUBSENTRY_INSTALL_SCRIPT_URL:-https://raw.githubusercontent.com/YuWan-030/subsentry-public/main/scripts/install-linux.sh}"

export SUBSENTRY_INSTALL_NGINX="${SUBSENTRY_INSTALL_NGINX:-false}"
export SUBSENTRY_BACKEND_PORT="${SUBSENTRY_BACKEND_PORT:-4398}"
export SUBSENTRY_DEFAULT_INSTALL_DIR="${SUBSENTRY_DEFAULT_INSTALL_DIR:-/opt/subsentry}"
export SUBSENTRY_REPO_URL="${SUBSENTRY_REPO_URL:-https://github.com/YuWan-030/subsentry-public.git}"
export SUBSENTRY_ARCHIVE_URL="${SUBSENTRY_ARCHIVE_URL:-https://github.com/YuWan-030/subsentry-public/archive/refs/heads/main.tar.gz}"

curl -fsSL "$SCRIPT_URL" | bash
