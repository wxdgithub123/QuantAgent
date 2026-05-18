#!/bin/bash
echo "PWD=$(pwd)"
echo "PATH=$PATH"
echo "PYTHON=$(which python)"
echo "PYVER=$(python --version)"
echo "---pandas---"
python -c "import pandas; print('pandas', pandas.__version__)"
echo "---PASSWORD---"
python -c "open('/home/hummingbot/conf/.password_verification').read()[:10]; print('PASSWORD OK')"
echo "---CONST_PATH---"
python -c "from hummingbot.client.config.config_crypt import PASSWORD_VERIFICATION_PATH; print('CONST_PATH:', PASSWORD_VERIFICATION_PATH)"
echo "---QUICKSTART---"
python ./bin/hummingbot_quickstart.py 2>&1 | tail -5
echo "EXIT: $?"
