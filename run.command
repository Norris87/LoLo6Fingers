#!/bin/bash
# Runs the app straight from the source code (no build needed).
# Must sit in the SAME folder as lolo6fingers.py and the ytenv folder.

cd "$(dirname "$0")"

if [ ! -f "ytenv/bin/activate" ]; then
    echo "The 'ytenv' virtual environment does not exist."
    echo "Run setup.command first."
    echo ""
    read -p "Press Enter to close..."
    exit 1
fi

# A venv stores its absolute path — after renaming or moving the folder
# it stops working and has to be rebuilt by setup.command
if ! grep -qF "$(pwd)/ytenv" ytenv/bin/activate; then
    echo "The folder was renamed or moved, so 'ytenv' no longer works."
    echo "Run setup.command once — it rebuilds it automatically."
    echo ""
    read -p "Press Enter to close..."
    exit 1
fi

source ytenv/bin/activate
python lolo6fingers.py
