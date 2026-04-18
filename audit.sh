#!/bin/bash
# Claude 4-Layer Memory System - Pre-Installation Audit (Linux/Mac)

echo ""
echo "Running pre-installation audit..."
echo ""

python3 audit.py

if [ $? -ne 0 ]; then
    echo ""
    echo "[ERROR] Audit found critical issues"
    echo "Please resolve them before installing"
    exit 1
fi

echo ""
echo "[OK] Audit passed! Ready to install."
echo ""
echo "Run ./install.sh to proceed with installation"
