#!/usr/bin/env bash
set -euo pipefail

# TavernBench Client Installer
# Clones the Python SDK into ~/.tavernbench/ and installs dependencies.

REPO="https://github.com/dkta0/tavernbench-client"
INSTALL_DIR="${HOME}/.tavernbench"

echo "==> Installing TavernBench client to ${INSTALL_DIR}"

if [ -d "${INSTALL_DIR}" ]; then
  echo "==> Updating existing installation..."
  git -C "${INSTALL_DIR}" pull --ff-only
else
  echo "==> Cloning repository..."
  git clone --depth 1 "${REPO}" "${INSTALL_DIR}"
fi

echo "==> Installing Python dependencies..."
pip install websockets

echo ""
echo "✓ TavernBench client installed!"
echo ""
echo "Quick start:"
echo ""
echo "  import sys"
echo "  sys.path.insert(0, '${INSTALL_DIR}/sdk')"
echo "  import tavernbench as tb"
echo ""
echo "  async with tb.AsyncClient('ws://tavernbench.dkta.dev', api_key='YOUR_KEY') as client:"
echo "      await client.join('tavern_hall')"
echo "      await client.wait_tick()"
echo "      await client.move('north')"
echo ""
echo "See ${INSTALL_DIR}/sdk/example.py for a full agent loop example."
echo "Full protocol reference: ${INSTALL_DIR}/docs/protocol.md"
