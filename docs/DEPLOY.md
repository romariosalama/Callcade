# Putting Callcade online (AWS Lightsail)

How the live site runs: one small Lightsail server with Ubuntu. The app runs as a service (`deploy/callcade.service`), and Caddy sits in front of it to handle HTTPS, which the mic needs to work in the browser. The database is the same SQLite file, kept on the server.

## 1. Server

Lightsail → **Create instance** → **Linux/Unix** → **OS Only** → **Ubuntu 24.04 LTS**. The 1 GB plan ($7/month) is plenty. Name it `callcade`.

Then:
- **Networking** tab → **Attach static IP**, so the address never changes.
- Same tab, **IPv4 Firewall** → add a rule for **HTTPS (443)**. SSH (22) and HTTP (80) are already open.

## 2. Domain

Point the domain at the static IP with two `A` records: one for the domain itself (`@`) and one for `www`. If the domain is in Route 53, this is under **Hosted zones**.

## 3. Install

Lightsail → the instance → **Connect using SSH** opens a terminal in the browser. Then:

```bash
git clone https://github.com/romariosalama/callcade.git
sudo bash callcade/deploy/setup.sh yourdomain.com
nano callcade/.env        # paste GROQ_API_KEY=..., then Ctrl+O, Enter, Ctrl+X
sudo systemctl restart callcade
```

Give Caddy a minute to get the certificate, then open `https://yourdomain.com`.

Make yourself admin (after signing up on the site):

```bash
cd callcade/backend && ../.venv/bin/python admin.py admin yourusername
```

## Updating the live site

Push to GitHub from your computer, then on the server:

```bash
bash callcade/deploy/update.sh
```

## Useful commands

| | |
| --- | --- |
| Is it running? | `sudo systemctl status callcade` |
| See the app's logs | `sudo journalctl -u callcade -n 50` |
| Restart after changing `.env` | `sudo systemctl restart callcade` |
| HTTPS problems | `sudo journalctl -u caddy -n 50` |

Back up the database with Lightsail snapshots (instance → **Snapshots** → turn on automatic snapshots).
