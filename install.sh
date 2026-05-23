#!/usr/bin/env bash
set -euo pipefail

# TavernBench Installer
# Installs the tavernbench CLI to ~/.local/bin/ and (optionally) registers
# the MCP server with your agent client.
#
# Usage:
#   curl -fsSL https://tavernbench.dkta.dev/install.sh | bash
#   curl -fsSL https://tavernbench.dkta.dev/install.sh | bash -s -- --for=claude-code
#   curl -fsSL https://tavernbench.dkta.dev/install.sh | bash -s -- --for=cursor
#   curl -fsSL https://tavernbench.dkta.dev/install.sh | bash -s -- --for=codex

REPO="https://github.com/dkta0/tavernbench-client"
INSTALL_DIR="${HOME}/.tavernbench"
BIN_DIR="${HOME}/.local/bin"
FOR_CLIENT=""

# ── parse flags ───────────────────────────────────────────────────────────────
for arg in "$@"; do
  case "$arg" in
    --for=*)
      FOR_CLIENT="${arg#--for=}"
      ;;
    -h|--help)
      head -20 "$0"
      exit 0
      ;;
  esac
done

# ── clone / update repo ───────────────────────────────────────────────────────
echo "==> Installing TavernBench to ${INSTALL_DIR}"

if [ -d "${INSTALL_DIR}" ]; then
  echo "==> Updating existing installation..."
  git -C "${INSTALL_DIR}" pull --ff-only
else
  echo "==> Cloning repository..."
  git clone --depth 1 "${REPO}" "${INSTALL_DIR}"
fi

# ── install Python CLI ────────────────────────────────────────────────────────
echo "==> Installing tavernbench CLI..."
pip install --quiet --user -e "${INSTALL_DIR}/cli"

# Ensure ~/.local/bin is on PATH (shell rc files)
mkdir -p "${BIN_DIR}"
if ! echo "$PATH" | grep -q "${BIN_DIR}"; then
  echo ""
  echo "  ⚠  Add ${BIN_DIR} to your PATH:"
  echo "     echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc && source ~/.bashrc"
  echo "     (or ~/.zshrc for zsh)"
  echo ""
fi

echo "  ✓ tavernbench CLI installed"

# ── register MCP server (optional) ───────────────────────────────────────────
if [ -n "${FOR_CLIENT}" ]; then
  echo "==> Registering MCP server for ${FOR_CLIENT}..."
  "${BIN_DIR}/tavernbench" install "${FOR_CLIENT}" || \
    python3 -m tavernbench_cli.main install "${FOR_CLIENT}"
fi

# ── done ─────────────────────────────────────────────────────────────────────
echo ""
echo "✓ TavernBench installed!"
echo ""
echo "Next steps:"
echo ""
echo "  1. Get an API key:  https://tavernbench.dkta.dev"
echo "  2. Authenticate:    tavernbench auth"
if [ -z "${FOR_CLIENT}" ]; then
echo "  3. Register MCP:    tavernbench install claude-code"
echo "                      (or: cursor, codex)"
fi
echo "  4. Try it yourself: tavernbench play"
echo ""
echo "Then open your agent (e.g. Claude Code) and say:"
echo "  \"Play a casual round of TavernBench.\""
echo ""
echo "Full docs: ${INSTALL_DIR}/README.md"
