#!/bin/bash
# Reticulum Node Manager — Dependency Installer
# For Ubuntu Server 24.04 LTS (Noble Numbat)
# Tested on x86_64 (Wyse 3040, standard PCs) and arm64 (Raspberry Pi 4/5)

set -e

# Resolve repo root immediately, before any cd commands change the working directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
ORIGINAL_DIR="$(pwd)"

echo "============================================="
echo " Reticulum Node Manager — Dependency Installer"
echo " Target: Ubuntu Server 24.04 LTS"
echo "============================================="
echo ""

# ── System packages ────────────────────────────────────
echo "[1/6] Installing system packages..."
sudo apt-get update
sudo apt-get install -y \
    git build-essential cmake \
    portaudio19-dev \
    python3 python3-dev python3-pip python3-venv \
    libhamlib-utils libhamlib-dev \
    direwolf \
    alsa-utils \
    pipx

# ── PATH setup ─────────────────────────────────────────
# pipx and pip --user install binaries to ~/.local/bin
# which is NOT in PATH by default on Ubuntu Server 24.04
echo ""
echo "[*] Configuring PATH..."
pipx ensurepath

if ! grep -q 'export PATH="$HOME/.local/bin:$PATH"' ~/.bashrc 2>/dev/null; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
fi
export PATH="$HOME/.local/bin:$PATH"

# Configure pip to allow system-wide installs if needed
mkdir -p ~/.config/pip
cat > ~/.config/pip/pip.conf << 'PIPEOF'
[global]
break-system-packages = true
PIPEOF

# ── Codec2 (build from source for DATAC4 modem support) ─
# The Ubuntu packaged libcodec2 does NOT include DATAC4.
echo ""
echo "[2/6] Building codec2 from source..."
CODEC2_DIR="$HOME/codec2"
if [ -d "$CODEC2_DIR" ]; then
    echo "  Updating existing codec2 repo..."
    cd "$CODEC2_DIR" && git pull
else
    echo "  Cloning codec2..."
    git clone https://github.com/drowe67/codec2.git "$CODEC2_DIR"
fi
cd "$CODEC2_DIR"
mkdir -p build_linux && cd build_linux
cmake ..
make -j$(nproc)
sudo make install
sudo ldconfig

# Verify libcodec2 is findable
if ! ldconfig -p | grep -q libcodec2; then
    echo "  Adding /usr/local/lib to ldconfig..."
    echo "/usr/local/lib" | sudo tee /etc/ld.so.conf.d/codec2.conf > /dev/null
    sudo ldconfig
fi

# ── FreeDV TNC2 ───────────────────────────────────────
echo ""
echo "[3/6] Installing FreeDV TNC2..."
pipx install freedvtnc2

# ── Reticulum Network Stack ───────────────────────────
echo ""
echo "[4/6] Installing Reticulum (RNS)..."
pipx install rns

# ── Reticulum Node Manager ───────────────────────────
echo ""
echo "[5/6] Installing Reticulum Node Manager..."

# Find the repo root (SCRIPT_DIR was resolved at top of script before any cd)
REPO_ROOT=""

# Try 1: relative to script location (normal case)
if [ -f "$SCRIPT_DIR/../pyproject.toml" ]; then
    REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

# Try 2: original working directory (user ran: cd repo && bash scripts/install-deps.sh)
if [ -z "$REPO_ROOT" ] && [ -f "$ORIGINAL_DIR/pyproject.toml" ]; then
    REPO_ROOT="$ORIGINAL_DIR"
fi

if [ -z "$REPO_ROOT" ]; then
    echo ""
    echo "  ERROR: Could not find pyproject.toml"
    echo ""
    echo "  Make sure you cloned the full repo and run from inside it:"
    echo "    git clone <repo-url>"
    echo "    cd rnm"
    echo "    bash scripts/install-deps.sh"
    echo ""
    exit 1
fi

pipx install "$REPO_ROOT"
echo "  Installed from local repo: $REPO_ROOT"

# ── Verification ──────────────────────────────────────
echo ""
echo "[6/6] Verifying installations..."
echo ""
ALL_OK=true
for cmd in direwolf freedvtnc2 rigctld rnsd rnm; do
    if command -v "$cmd" &>/dev/null; then
        VERSION=$("$cmd" --version 2>/dev/null | head -1 || echo "installed")
        echo "  OK  $cmd  ($VERSION)"
    else
        echo "  MISSING  $cmd"
        ALL_OK=false
    fi
done

# Verify alsa-utils for audio device detection
if command -v aplay &>/dev/null; then
    echo "  OK  aplay  (alsa-utils — audio device detection)"
else
    echo "  MISSING  aplay (alsa-utils)"
    ALL_OK=false
fi

echo ""
if $ALL_OK; then
    echo "All dependencies installed successfully!"
    echo ""
    echo "Next steps:"
    echo "  1. Plug in your USB audio interfaces and serial/CAT adapters"
    echo "  2. Run: rnm devices audio    (list audio devices)"
    echo "  3. Run: rnm devices serial   (list serial devices)"
    echo "  4. Run: rnm setup            (interactive configuration wizard)"
    echo "  5. Run: rnm start            (launch all services)"
else
    echo "Some dependencies are missing — check the errors above."
    exit 1
fi
