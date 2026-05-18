#!/bin/bash
echo "=== PASSWORD FILE ==="
conda run -n hummingbot python -c "open('/home/hummingbot/conf/.password_verification').read()[:20]; print('PASSWORD FILE OK')"
echo "=== QUICKSTART ==="
conda run -n hummingbot ./bin/hummingbot_quickstart.py 2>&1 | tail -15
echo "EXIT: $?"
