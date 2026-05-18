#!/bin/bash
echo "=== STEP 1: Check file ==="
ls -la /home/hummingbot/conf/.password_verification
echo "=== STEP 2: Python read ==="
/opt/conda/envs/hummingbot/bin/python -c "open('/home/hummingbot/conf/.password_verification').read()[:20]; print('PASSWORD OK')"
echo "=== STEP 3: Quickstart ==="
/opt/conda/envs/hummingbot/bin/python ./bin/hummingbot_quickstart.py 2>&1 | tail -10
echo "EXIT: $?"
