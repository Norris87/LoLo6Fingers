#!/bin/bash
# ==============================================================
#  PO TOKEN PROVIDER — fixes "storyboards only" / SABR blocking
# ==============================================================
# YouTube now requires a so-called PO Token (Proof of Origin).
# When yt-dlp does not have one, YouTube hides all video formats and
# sends only storyboards (sb0/sb1/sb2) — it looks as if the video
# were unavailable.
#
# This script installs the official bgutil POT provider.
# Run it once. Works for the app started from source (run.command).

cd "$(dirname "$0")"
PROJECT="$(pwd)"
TARGET="$HOME/bgutil-ytdlp-pot-provider"   # default location the plugin finds itself

echo "=============================================="
echo "   PO Token provider setup"
echo "=============================================="
echo ""

if [ ! -f "ytenv/bin/activate" ]; then
    echo "❌ The 'ytenv' virtual environment does not exist."
    echo "   Run setup.command first"
    read -p "Press Enter to close..."
    exit 1
fi

# ---------------------------------------------------------------
# 1. git
# ---------------------------------------------------------------
echo "--- Step 1/4: git ---"
if ! command -v git &>/dev/null; then
    echo "❌ git is not installed."
    echo "   Open Terminal and run:  xcode-select --install"
    echo "   Then run this script again."
    read -p "Press Enter to close..."
    exit 1
fi
echo "✅ git: $(git --version)"

# ---------------------------------------------------------------
# 2. Node.js (>= 22)
# ---------------------------------------------------------------
# The PO token provider is fine with Node 20, but yt-dlp also uses Node to
# solve YouTube challenges and there it needs 22+. Older Node would be
# silently ignored by yt-dlp.
echo ""
echo "--- Step 2/4: Node.js ---"
NODE_OK=0
if command -v node &>/dev/null; then
    NODE_VER=$(node -v | sed 's/v//' | cut -d. -f1)
    if [ "$NODE_VER" -ge 22 ] 2>/dev/null; then
        echo "✅ Node.js $(node -v)"
        NODE_OK=1
    else
        echo "⚠︎  Node.js $(node -v) is too old (22+ needed)"
    fi
fi

if [ "$NODE_OK" = "0" ]; then
    if command -v brew &>/dev/null; then
        echo "Installing / updating Node.js with Homebrew..."
        brew install node 2>/dev/null; brew upgrade node 2>/dev/null
        NODE_VER=$(node -v 2>/dev/null | sed 's/v//' | cut -d. -f1)
        if [ "$NODE_VER" -ge 22 ] 2>/dev/null; then
            echo "✅ Node.js $(node -v)"
        else
            echo "❌ Could not install Node.js 22+"; read -p "Press Enter..."; exit 1
        fi
    else
        echo "❌ Node.js is missing and Homebrew is not installed."
        echo ""
        echo "   Install one of these and run the script again:"
        echo "   • Homebrew:  https://brew.sh"
        echo "   • Node.js:   https://nodejs.org  (version 22 or newer)"
        read -p "Press Enter to close..."
        exit 1
    fi
fi

# ---------------------------------------------------------------
# 3. yt-dlp plugin (also decides the provider version)
# ---------------------------------------------------------------
echo ""
echo "--- Step 3/4: yt-dlp plugin ---"
source ytenv/bin/activate
pip install -U bgutil-ytdlp-pot-provider --quiet \
    || { echo "❌ Installing the plugin failed"; read -p "Press Enter..."; exit 1; }

PLUGIN_VERSION=$(pip show bgutil-ytdlp-pot-provider 2>/dev/null \
                 | grep -i '^Version:' | awk '{print $2}')
echo "✅ Plugin installed, version $PLUGIN_VERSION"

# ---------------------------------------------------------------
# 4. Provider (must be the SAME version as the plugin)
# ---------------------------------------------------------------
echo ""
echo "--- Step 4/4: provider ---"

if [ -d "$TARGET" ]; then
    echo "Folder $TARGET already exists — reinstalling..."
    rm -rf "$TARGET"
fi

echo "Downloading provider version $PLUGIN_VERSION..."
git clone --quiet --single-branch --branch "$PLUGIN_VERSION" \
    https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git "$TARGET" 2>/dev/null

if [ ! -d "$TARGET/server" ]; then
    echo "   Version $PLUGIN_VERSION not found, trying the main branch..."
    rm -rf "$TARGET"
    git clone --quiet --depth 1 \
        https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git "$TARGET" \
        || { echo "❌ Download failed"; read -p "Press Enter..."; exit 1; }
fi

cd "$TARGET/server" || { echo "❌ server folder not found"; read -p "Press Enter..."; exit 1; }

echo "Installing dependencies (the longest part, 2-3 minutes)..."
npm ci --silent 2>&1 | tail -3

echo "Compiling..."
npx tsc 2>&1 | tail -3

if [ -f "build/generate_once.js" ] || [ -d "build" ]; then
    echo "✅ Provider ready in $TARGET"
else
    echo "❌ Compilation failed — see the errors above"
    read -p "Press Enter to close..."
    exit 1
fi

# ---------------------------------------------------------------
# Verification
# ---------------------------------------------------------------
cd "$PROJECT"
echo ""
echo "--- Verification ---"
echo "Checking whether yt-dlp sees the plugin..."
OUTPUT=$(python -m yt_dlp -v "https://www.youtube.com/watch?v=dQw4w9WgXcQ" \
         --simulate 2>&1 | grep -i "PO Token Providers" | head -1)

if [ -n "$OUTPUT" ]; then
    echo "✅ $OUTPUT"
else
    echo "⚠︎  The plugin did not show up in the list. That may still be fine —"
    echo "   test it in the app with 'What can be downloaded?'"
fi

echo ""
echo "=============================================="
echo "  ✅ DONE"
echo ""
echo "  Start the app with run.command and try a video"
echo "  that did not download before."
echo ""
echo "  NOTE: this works for the app started from source."
echo "  It does not work in the bundled .app — plugins"
echo "  are not packaged into it."
echo "=============================================="
echo ""
read -p "Press Enter to close..."
