#!/bin/bash
# Script per eliminare file .txt di 0 byte nella cartella /opt/kbsearch/logs/ocr

TARGET_DIR="/opt/kbsearch/logs/ocr"

# Trova ed elimina i file .txt di 0 byte
#

sudo find "$TARGET_DIR" -type f -name "*.txt" -size 0c -exec rm -f {} \;

