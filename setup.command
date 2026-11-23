#!/bin/bash
# FIRST RUN — sets up everything that is not source code:
#   virtual environment, libraries, the icon and ffmpeg.
# Run it once. After that use run.command / package.command.

cd "$(dirname "$0")"

echo "=============================================="
echo "   LoLo6Fingers — first-time setup"
echo "=============================================="
echo ""

ERRORS=0

# ---------------------------------------------------------------
# 1. Python
# ---------------------------------------------------------------
# yt-dlp 2026.10.26+ requires Python 3.11+. macOS ships Python 3.9 —
# pip would silently install an ancient yt-dlp on it that can no longer
# download from YouTube. So we look for a newer Python.
PY=""
for CANDIDATE in python3.14 python3.13 python3.12 python3.11 \
                 /opt/homebrew/bin/python3 /usr/local/bin/python3 python3; do
    if command -v "$CANDIDATE" &>/dev/null \
       && "$CANDIDATE" -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null; then
        PY="$(command -v "$CANDIDATE")"
        break
    fi
done

if [ -z "$PY" ]; then
    echo "❌ Python 3.11 or newer is missing."
    echo "   (the system has: $(python3 --version 2>&1) — too old for yt-dlp)"
    echo ""
    echo "   Install a newer Python in one of these ways:"
    echo "   • Homebrew:   brew install python"
    echo "   • or from:    https://www.python.org/downloads/"
    echo "   Then run setup.command again."
    read -p "Press Enter to close..."
    exit 1
fi
echo "✅ Python: $("$PY" --version)  ($PY)"

# An existing ytenv on an old Python has to be recreated
if [ -f "ytenv/bin/python" ] && ! ytenv/bin/python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null; then
    echo "⚠︎  ytenv uses an old Python ($(ytenv/bin/python --version 2>&1)) — recreating it"
    rm -rf ytenv
fi

# A venv stores its absolute path. After the folder is renamed or moved
# (e.g. cloned from GitHub elsewhere) 'activate' points to a path that no
# longer exists and the app would start on the wrong Python.
if [ -f "ytenv/bin/activate" ] && ! grep -qF "$(pwd)/ytenv" ytenv/bin/activate; then
    echo "⚠︎  The folder was renamed or moved — recreating ytenv"
    rm -rf ytenv
fi

# ---------------------------------------------------------------
# 2. Virtual environment + libraries
# ---------------------------------------------------------------
echo ""
echo "--- Step 1/4: virtual environment ---"
if [ ! -f "ytenv/bin/activate" ]; then
    echo "Creating ytenv..."
    "$PY" -m venv ytenv || { echo "❌ Could not create the venv"; exit 1; }
else
    echo "ytenv already exists."
fi

source ytenv/bin/activate
echo "Installing libraries (this takes a moment)..."
pip install --upgrade pip --quiet
# [default] matters: yt-dlp pins the exact yt-dlp-ejs version (the YouTube
# challenge solver). Without it the versions can drift apart.
pip install --upgrade "yt-dlp[default]" pyinstaller certifi pillow --quiet \
    && echo "✅ Libraries installed: yt-dlp $(python -c 'import yt_dlp; print(yt_dlp.version.__version__)')" \
    || { echo "❌ Installing the libraries failed"; ERRORS=1; }

# ---------------------------------------------------------------
# 3. Icon from icon-source.png
# ---------------------------------------------------------------
echo ""
echo "--- Step 2/4: icon ---"
if [ -f "icon.icns" ]; then
    echo "icon.icns already exists, skipping."
elif [ -f "icon-source.png" ]; then
    echo "Building icon.icns from icon-source.png..."
    rm -rf icon.iconset
    mkdir -p icon.iconset
    # Built-in macOS tools sips + iconutil — nothing to install
    for S in 16 32 128 256 512; do
        sips -z $S $S icon-source.png --out "icon.iconset/icon_${S}x${S}.png" &>/dev/null
        D=$((S * 2))
        sips -z $D $D icon-source.png --out "icon.iconset/icon_${S}x${S}@2x.png" &>/dev/null
    done
    iconutil -c icns icon.iconset -o icon.icns 2>/dev/null \
        && echo "✅ icon.icns created" \
        || { echo "❌ iconutil failed"; ERRORS=1; }
    rm -rf icon.iconset

    # Windows icon (for a possible Windows build)
    python - <<'PYEOF' 2>/dev/null && echo "✅ icon.ico created (for Windows)" || echo "   (could not create icon.ico — not needed for the Mac build)"
from PIL import Image
img = Image.open('icon-source.png')
img.save('icon.ico', format='ICO',
         sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
PYEOF
else
    echo "⚠︎  icon-source.png not found — no icon will be built."
    echo "   The app will work, it will just have the default icon."
fi

# ---------------------------------------------------------------
# 4. ffmpeg + ffprobe
# ---------------------------------------------------------------
echo ""
echo "--- Step 3/4: ffmpeg ---"
if [ -f "ffmpeg" ] && [ -f "ffprobe" ]; then
    echo "ffmpeg and ffprobe are already in the folder."
else
    FOUND=""
    # Try Homebrew or anything on the PATH
    for CANDIDATE in /opt/homebrew/bin/ffmpeg /usr/local/bin/ffmpeg "$(command -v ffmpeg 2>/dev/null)"; do
        if [ -n "$CANDIDATE" ] && [ -x "$CANDIDATE" ]; then
            FOUND="$CANDIDATE"
            break
        fi
    done

    if [ -n "$FOUND" ]; then
        DIR=$(dirname "$FOUND")
        echo "Found ffmpeg in $DIR — copying it here..."
        cp "$DIR/ffmpeg" ./ffmpeg 2>/dev/null
        cp "$DIR/ffprobe" ./ffprobe 2>/dev/null
        chmod +x ffmpeg ffprobe 2>/dev/null
        if [ -f "ffmpeg" ] && [ -f "ffprobe" ]; then
            echo "✅ ffmpeg and ffprobe copied"
        else
            echo "⚠︎  ffprobe was not found next to ffmpeg"
            ERRORS=1
        fi
    elif command -v brew &>/dev/null; then
        echo "ffmpeg is not installed, but you have Homebrew."
        read -p "Install it with brew? (y/n) [y]: " ANSWER
        ANSWER=${ANSWER:-y}
        if [ "$ANSWER" = "y" ] || [ "$ANSWER" = "Y" ]; then
            brew install ffmpeg
            cp /opt/homebrew/bin/ffmpeg ./ffmpeg 2>/dev/null || cp /usr/local/bin/ffmpeg ./ffmpeg 2>/dev/null
            cp /opt/homebrew/bin/ffprobe ./ffprobe 2>/dev/null || cp /usr/local/bin/ffprobe ./ffprobe 2>/dev/null
            chmod +x ffmpeg ffprobe 2>/dev/null
            [ -f "ffmpeg" ] && echo "✅ ffmpeg ready" || { echo "❌ failed"; ERRORS=1; }
        else
            ERRORS=1
        fi
    else
        echo "❌ ffmpeg not found and Homebrew is not installed."
        echo ""
        echo "   Two options:"
        echo "   A) Install Homebrew (https://brew.sh), then run setup again"
        echo "   B) Download ffmpeg and ffprobe manually from https://www.osxexperts.net"
        echo "      and copy both files into this folder"
        ERRORS=1
    fi
fi

# ---------------------------------------------------------------
# 5. Script permissions
# ---------------------------------------------------------------
echo ""
echo "--- Step 4/4: script permissions ---"
chmod +x *.command 2>/dev/null
echo "✅ Done"

# ---------------------------------------------------------------
echo ""
echo "=============================================="
if [ "$ERRORS" = "0" ]; then
    echo "  ✅ ALL SET"
    echo ""
    echo "  Run the app with:        run.command"
    echo "  Build the .app + zip:    package.command"
else
    echo "  ⚠︎  SETUP FINISHED WITH WARNINGS"
    echo ""
    echo "  See the errors above — most often ffmpeg is missing."
    echo "  Without it, re-encoding and merging will not work."
fi
echo "=============================================="
echo ""
read -p "Press Enter to close..."
