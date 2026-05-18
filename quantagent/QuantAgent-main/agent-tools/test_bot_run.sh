#!/bin/bash
echo "PWD=$(pwd)"
echo "PATH=$PATH"
echo "PYTHON=$(which python)"
echo "PYVER=$(python --version)"
conda run -n hummingbot python -c "import pandas; print('pandas OK')"
conda run -n hummingbot python -c "open('/home/hummingbot/conf/.password_verification').read()[:10]; print('PASSWORD OK')"
conda run -n hummingbot python -c "from hummingbot.client.config.config_crypt import PASSWORD_VERIFICATION_PATH; print('CONST_PATH:', PASSWORD_VERIFICATION_PATH)"
conda run -n hummingbot ./bin/hummingbot_quickstart.py 2>&1 | tail -5
echo "EXIT: $?"
