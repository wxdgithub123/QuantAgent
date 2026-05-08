#!/bin/bash
echo "PATH=$PATH"
echo "---"
conda run -n hummingbot echo "Inside conda: PATH=$PATH"
echo "---"
conda run -n hummingbot python -c "import pandas; print('pandas', pandas.__version__)"
echo "---PASSWORD---"
/opt/conda/envs/hummingbot/bin/python -c "open('/home/hummingbot/conf/.password_verification').read()[:20]; print('PASSWORD OK')"
echo "---QUICKSTART---"
conda run -n hummingbot ./bin/hummingbot_quickstart.py 2>&1 | tail -20
echo "EXIT: $?"
