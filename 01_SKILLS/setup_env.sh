#!/bin/bash
# DeParadigm Media Environment Setup Script
# Initializes a local Python virtual environment and installs verified
# local-first dependencies for the skills.py background platform.
# Designed to run fully separated from native macOS system libraries.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$PROJECT_ROOT/.venv"

echo "[+] DeParadigm Media Environment Setup"
echo "    Project root: $PROJECT_ROOT"
echo "    Venv target:  $VENV_DIR"

# ---------------------------------------------------------------------------
# Step 1: Create virtual environment
# ---------------------------------------------------------------------------
if [ -d "$VENV_DIR" ]; then
    echo "[!] Existing .venv found at $VENV_DIR"
    echo "    Remove it first if you want a clean reinstall."
else
    echo "[*] Creating Python virtual environment..."
    python3 -m venv "$VENV_DIR"
    echo "[+] Virtual environment created."
fi

# ---------------------------------------------------------------------------
# Step 2: Activate and upgrade pip
# ---------------------------------------------------------------------------
echo "[*] Activating virtual environment and upgrading pip..."
source "$VENV_DIR/bin/activate"
pip install --upgrade pip setuptools wheel

# ---------------------------------------------------------------------------
# Step 3: Install verified local-first dependency layers
# ---------------------------------------------------------------------------
echo "[*] Installing accelerated ML workpacks..."

# Native Apple Silicon hardware acceleration libraries
pip install mlx mlx-lm

# Secure local loopback oMLX server calls
pip install urllib3 certifi

# Raw text queue ingestion
pip install beautifulsoup4 html5lib

# Frontmatter block parsing for agent skills
pip install PyYAML

echo "[+] All dependencies installed."

# ---------------------------------------------------------------------------
# Step 4: Freeze requirements
# ---------------------------------------------------------------------------
REQUIREMENTS_FILE="$PROJECT_ROOT/requirements.txt"
echo "[*] Freezing requirements to $REQUIREMENTS_FILE..."
pip freeze > "$REQUIREMENTS_FILE"
echo "[+] Requirements frozen."

# ---------------------------------------------------------------------------
# Step 5: Verification
# ---------------------------------------------------------------------------
echo "[*] Verifying installed packages..."
python3 -c "
import importlib
packages = ['mlx', 'mlx_lm', 'urllib3', 'certifi', 'bs4', 'html5lib', 'yaml']
for pkg in packages:
    try:
        importlib.import_module(pkg)
        print(f'    [PASS] {pkg}')
    except ImportError as e:
        print(f'    [FAIL] {pkg}: {e}')
"

echo ""
echo "[+] Setup complete."
echo "    To activate: source $VENV_DIR/bin/activate"
echo "    To run skills.py: python3 01_SKILLS/skills.py"
echo "    To run media bridge: python3 01_SKILLS/solocorn_media_bridge.py"