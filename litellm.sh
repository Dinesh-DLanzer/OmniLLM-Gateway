#!/bin/bash

# Prevent PM2 from weird env issues
unset PORT

# DB
# export DATABASE_URL="postgresql://litellm:litellm@127.0.0.1:5432/litellm"
# login
export UI_USERNAME=$(grep '^UI_USERNAME=' .env | cut -d'=' -f2- | sed 's/[[:space:]]*#.*$//')
export UI_PASSWORD=$(grep '^UI_PASSWORD=' .env | cut -d'=' -f2- | sed 's/[[:space:]]*#.*$//')

# Keep process alive properly
exec litellm \
  --config /etc/litellm/config.yaml \
  --host 0.0.0.0 \
  --port 4000