#!/bin/bash
# Installed to ~/.studio-backup.sh (OUTSIDE ~/Documents so launchd can exec it).
# /bin/bash has Full Disk Access, so it can cd into and read ~/Documents at runtime.
cd /Users/nazeera/Documents/AI_PRODUCER || exit 1
exec ./studio backup >> logs/backup.log 2>&1
