#!/bin/sh
set -e
cd /app

echo "Checking dependencies..."
if [ ! -d "/app/node_modules/.package-lock.json" ] || [ "$(md5sum /app/package.json | awk '{print $1}')" != "$(cat /app/.package.json.md5 2>/dev/null || echo '')" ]; then
    echo "Installing dependencies..."
    npm config set registry https://registry.npmmirror.com && npm install
    md5sum /app/package.json | awk '{print $1}' > /app/.package.json.md5
fi

echo "Building production bundle..."
npx next build

echo "Starting production server with 10min proxy timeout..."
exec node server.js
