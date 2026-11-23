#!/bin/bash
# Full build: update yt-dlp -> Deno -> build the .app -> zip ready to share
cd "$(dirname "$0")"

if [ ! -f "ytenv/bin/activate" ]; then
    echo "The 'ytenv' virtual environment does not exist — run setup.command first"
    read -p "Press Enter to close..."
    exit 1
fi

source ytenv/bin/activate

APP_NAME="LoLo6Fingers"
VERSION=$(grep '^VERSION = ' lolo6fingers.py | cut -d'"' -f2)
ZIP_NAME="${APP_NAME}-${VERSION}-macOS.zip"
ZIP_OUT="$(pwd)/$ZIP_NAME"

echo "======================================"
echo "  $APP_NAME packager — version $VERSION"
echo "======================================"
echo ""

# 1. Update yt-dlp (so the bundled app has the newest extractor)
echo "Step 1/4 — Updating yt-dlp..."
BEFORE=$(python -c "import yt_dlp; print(yt_dlp.version.__version__)" 2>/dev/null || echo "?")
# [default] matters: yt-dlp pins the exact yt-dlp-ejs version (the YouTube
# challenge solver). Without it ejs would not update and on a version
# mismatch yt-dlp stops solving challenges — formats go missing.
pip install -U "yt-dlp[default]" --quiet 2>&1 | grep -v "^$"
AFTER=$(python -c "import yt_dlp; print(yt_dlp.version.__version__)" 2>/dev/null || echo "?")
if [ "$BEFORE" = "$AFTER" ]; then
    echo "   yt-dlp already up to date: $AFTER"
else
    echo "   yt-dlp: $BEFORE -> $AFTER ✅"
fi
echo ""

# 2. Deno — JavaScript runtime bundled into the .app. Without it yt-dlp
#    tries only one YouTube client (visionos) and many videos fail.
echo "Step 2/4 — Deno (JavaScript runtime for YouTube)..."
if [ -x "./deno" ] && ./deno --version &>/dev/null; then
    echo "   Deno already present: $(./deno --version | head -1)"
else
    DENO_ZIP="deno-aarch64-apple-darwin.zip"
    DENO_URL="https://github.com/denoland/deno/releases/latest/download/$DENO_ZIP"
    TMP_DENO=$(mktemp -d)
    echo "   Downloading from the official Deno Land GitHub..."
    if curl -fsSL "$DENO_URL" -o "$TMP_DENO/$DENO_ZIP" \
       && curl -fsSL "$DENO_URL.sha256sum" -o "$TMP_DENO/sum.txt"; then
        EXPECTED=$(awk '{print $1}' "$TMP_DENO/sum.txt" | tr 'A-F' 'a-f')
        ACTUAL=$(shasum -a 256 "$TMP_DENO/$DENO_ZIP" | awk '{print $1}')
        if [ -n "$EXPECTED" ] && [ "$EXPECTED" = "$ACTUAL" ]; then
            mkdir -p "$TMP_DENO/x"
            unzip -q "$TMP_DENO/$DENO_ZIP" -d "$TMP_DENO/x"
            mv "$TMP_DENO/x/deno" ./deno && chmod +x ./deno
            echo "   ✅ Deno ready: $(./deno --version | head -1)"
        else
            echo "   ❌ Checksum mismatch — Deno will NOT be used (security)."
        fi
    else
        echo "   ⚠︎  Could not download Deno — the .app will be built without it."
    fi
    rm -rf "$TMP_DENO"
fi
echo ""

# 3. Make sure PyInstaller is there and build
if ! python -m PyInstaller --version &>/dev/null; then
    echo "   Installing PyInstaller..."
    pip install pyinstaller --quiet
fi

echo "Step 3/4 — Building the .app (1-2 minutes)..."
rm -rf build
python -m PyInstaller "$APP_NAME.spec" --noconfirm --clean 2>&1 | grep -E ">>>|ERROR|completed successfully" | tail -4

if [ ! -d "dist/$APP_NAME.app" ]; then
    echo ""
    echo "❌ Build failed. Check the errors above."
    read -p "Press Enter to close..."
    exit 1
fi
echo "   Build OK"
echo ""

# 4. Zip the app + docs
echo "Step 4/4 — Zipping the app and the docs..."
rm -f "$ZIP_OUT"

BUNDLE="$APP_NAME $VERSION"
STAGE="dist/$BUNDLE"
rm -rf "$STAGE"
mkdir -p "$STAGE"

# ditto (not cp) — keeps macOS metadata and permissions of the .app bundle
ditto "dist/$APP_NAME.app" "$STAGE/$APP_NAME.app"

for DOC in "INSTALL.md" "COOKIES.md" "CHANGELOG.md" "LICENSE"; do
    if [ -f "$DOC" ]; then
        cp "$DOC" "$STAGE/"
        echo "   Included: $DOC"
    fi
done

cd dist
ditto -c -k --sequesterRsrc --keepParent "$BUNDLE" "$ZIP_OUT"
cd ..
rm -rf "$STAGE"

SIZE=$(du -sh "$ZIP_OUT" | cut -f1)

echo ""
echo "======================================"
echo "  ✅ DONE — $ZIP_NAME ($SIZE)"
echo "======================================"
echo ""
echo "File to share / attach to a GitHub Release:"
echo "   $ZIP_OUT"
echo ""

open -R "$ZIP_OUT"
read -p "Press Enter to close..."
