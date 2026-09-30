#!/bin/bash
# One-time setup for Callcade on a fresh Ubuntu 24.04 Lightsail server.
# Run it from the home folder after cloning the repo:
#   sudo bash callcade/deploy/setup.sh yourdomain.com
set -e

DOMAIN="$1"
if [ -z "$DOMAIN" ]; then
  echo "usage: sudo bash callcade/deploy/setup.sh yourdomain.com"
  exit 1
fi
APP=/home/ubuntu/callcade

# a swap file, so installing packages doesn't run out of memory on the small plans
if [ ! -f /swapfile ]; then
  fallocate -l 1G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo "/swapfile none swap sw 0 0" >> /etc/fstab
fi

apt-get update
apt-get install -y python3-venv caddy

sudo -u ubuntu python3 -m venv $APP/.venv
sudo -u ubuntu $APP/.venv/bin/pip install -r $APP/requirements.txt

# start .env from the example with the production settings. the Groq key gets added by hand after
if [ ! -f $APP/.env ]; then
  sudo -u ubuntu cp $APP/.env.example $APP/.env
  sed -i "s|^CALLCADE_MODE=.*|CALLCADE_MODE=groq|; s|^SITE_URL=.*|SITE_URL=https://$DOMAIN|" $APP/.env
  chmod 600 $APP/.env
fi

# run the app as a service, so it starts when the server boots and restarts if it crashes
cp $APP/deploy/callcade.service /etc/systemd/system/callcade.service
systemctl daemon-reload
systemctl enable callcade

# Caddy gets the HTTPS certificate (and renews it) on its own, then passes requests to the app
sed "s/DOMAIN/$DOMAIN/g" $APP/deploy/Caddyfile > /etc/caddy/Caddyfile
systemctl restart caddy

echo
echo "Setup done. Last step, add your Groq key:"
echo "  nano $APP/.env"
echo "then start it:"
echo "  sudo systemctl restart callcade"
