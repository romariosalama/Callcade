#!/bin/bash
# get the latest code from GitHub and restart the app. run it on the server:
#   bash ~/callcade/deploy/update.sh
set -e
cd /home/ubuntu/callcade
git pull
.venv/bin/pip install -q -r requirements.txt
sudo systemctl restart callcade
echo "Updated and restarted."
