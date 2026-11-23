#!/bin/bash
# Updates yt-dlp. Offers the stable version or a nightly build.
cd "$(dirname "$0")"

if [ ! -f "ytenv/bin/activate" ]; then
    echo "The 'ytenv' virtual environment does not exist — run setup.command first"
    read -p "Press Enter to close..."
    exit 1
fi

source ytenv/bin/activate

echo "=== Updating yt-dlp ==="
echo ""

BEFORE=$(python -c "import yt_dlp; print(yt_dlp.version.__version__)" 2>/dev/null || echo "unknown")
echo "You have now: $BEFORE"
echo ""
echo "Choose:"
echo "  1) Stable version  (recommended)"
echo "  2) Nightly build   (newer YouTube fixes, may be less tested)"
echo ""
read -p "Enter 1 or 2 [1]: " CHOICE
CHOICE=${CHOICE:-1}
echo ""

# [default] is required: yt-dlp pins the exact yt-dlp-ejs version (the
# YouTube challenge solver). Without it ejs would stay old and on a version
# mismatch yt-dlp stops solving challenges — formats then go missing.
if [ "$CHOICE" = "2" ]; then
    echo "Installing the nightly build..."
    # NOTE: this ONE command is enough. Installing from the GitHub master
    # tarball on top of it would revert the result to the stable version.
    pip install -U --pre "yt-dlp[default]" 2>&1 | grep -vE "^\s*$|Requirement already"
else
    echo "Installing the latest stable version..."
    # --force-reinstall is needed when going back from a nightly build:
    # its version number is higher, so a plain -U would do nothing.
    if python -c "import yt_dlp,sys; sys.exit(0 if 'dev' in yt_dlp.version.__version__ or len(yt_dlp.version.__version__.split('.'))>3 else 1)" 2>/dev/null; then
        echo "(going back from a nightly build to the stable version)"
        pip install -U --force-reinstall "yt-dlp[default]" 2>&1 | grep -vE "^\s*$|Requirement already"
    else
        pip install -U "yt-dlp[default]" 2>&1 | grep -vE "^\s*$|Requirement already"
    fi
fi

AFTER=$(python -c "import yt_dlp; print(yt_dlp.version.__version__)" 2>/dev/null || echo "unknown")
echo ""
echo "You have now: $AFTER"
echo ""

if [ "$BEFORE" = "$AFTER" ]; then
    echo "You already had the latest version — nothing changed."
else
    echo "✅ Update successful!"
    echo ""
    echo "NOTE: to get the change into the .app as well, also run"
    echo "      package.command (it rebuilds the app)."
fi

echo ""
read -p "Press Enter to close..."
