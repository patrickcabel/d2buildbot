# Oracle Cloud Always Free — D2 Build Maker

Free **ARM VM with up to 24 GB RAM** (use ~2 OCPU / 12 GB for this app). Much safer than Render’s 512 MB free tier for Destiny inventory loads.

## 1. Create the VM

1. Sign up: https://www.oracle.com/cloud/free/
2. **Compute → Instances → Create instance**
3. Image: **Ubuntu 22.04** (or Oracle Linux) — **ARM (Ampere)** shape `VM.Standard.A1.Flex`
4. Shape: **2 OCPUs**, **12 GB RAM** (or more if available)
5. Networking: assign a **public IP**
6. Add your SSH public key
7. Create instance, note the **public IP**

## 2. Open firewall ports

In the subnet **Security List** (or NSG) for the VCN, ingress:

| Port | Source | Notes |
|------|--------|--------|
| 22 | your IP / 0.0.0.0/0 | SSH |
| 80 | 0.0.0.0/0 | HTTP (Let’s Encrypt) |
| 443 | 0.0.0.0/0 | HTTPS |

On the VM OS firewall (if enabled), allow 80/443 as well (`ufw allow 80,443/tcp`).

## 3. SSH and install

```bash
ssh ubuntu@YOUR_PUBLIC_IP
# (Oracle Linux often uses: ssh opc@YOUR_PUBLIC_IP)

git clone https://github.com/patrickcabel/d2buildbot.git
cd d2buildbot
bash deploy/oracle/setup.sh
```

Edit credentials:

```bash
nano ~/d2buildbot/deploy/oracle/.env
```

Fill in `BUNGIE_API_KEY`, `BUNGIE_CLIENT_ID`, `BUNGIE_CLIENT_SECRET`.  
`DOMAIN` / `PUBLIC_BASE_URL` are auto-filled from your public IP via [sslip.io](https://sslip.io) (e.g. `https://130-162-10-20.sslip.io`).

Start:

```bash
cd ~/d2buildbot/deploy/oracle
docker compose up -d --build
```

First build takes several minutes (Node + Python image).

## 4. Bungie OAuth

In https://www.bungie.net/en/Application set **Redirect URL** exactly to:

```text
https://YOUR-IP-WITH-DASHES.sslip.io/api/auth/callback
```

(same value as `PUBLIC_BASE_URL` + `/api/auth/callback` in `.env`).

## 5. Use the app

Open `PUBLIC_BASE_URL` → Login with Bungie → Sync Manifest → Inventory.

### Useful commands

```bash
cd ~/d2buildbot/deploy/oracle
docker compose logs -f app
docker compose ps
docker compose pull && git -C ~/d2buildbot pull && docker compose up -d --build
```

### Notes

- Data (manifest DB, sessions) lives in the `app-data` Docker volume.
- sslip.io needs no DNS account; for a custom domain, set `DOMAIN` / `PUBLIC_BASE_URL` and point an A record at the VM.
- Oracle may reclaim “idle” Always Free VMs — occasional light traffic or a healthcheck cron helps.
