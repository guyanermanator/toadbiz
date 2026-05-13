# Deploying Toad Business to Render

This guide walks you through deploying Toad Business to Render's free tier.

## Overview

Toad Business now uses a **server-only architecture** instead of P2P networking. This means:
- All players connect to a **single central server**
- The server hosts the game simulation and manages all game state
- Hosting works from anywhere (no local networking issues)
- **Better security** — your home IP is never exposed

## Prerequisites

1. **GitHub account** — Render deploys from GitHub
2. **Render account** — Sign up for free at [render.com](https://render.com)
3. **Python 3.9+** — Already on Render (included in deployment environment)

## Step 1: Push Code to GitHub

If you haven't already, initialize a Git repository and push to GitHub:

```bash
git init
git add .
git commit -m "Initial commit: Toad Business with server-only multiplayer"
git remote add origin https://github.com/YOUR_USERNAME/toadbusiness.git
git branch -M main
git push -u origin main
```

## Step 2: Create a Render Web Service

1. **Log in** to [render.com](https://render.com) and click **New +** → **Web Service**

2. **Connect your repository:**
   - Click "Connect a repo"
   - Search for your `toadbusiness` repository
   - Click "Connect"

3. **Configure the service:**
   - **Name:** `toadbusiness` (or your preferred name)
   - **Environment:** `Python 3`
   - **Region:** Choose closest to you (e.g., `Ohio` for US-East)
   - **Branch:** `main`
   - **Build Command:** 
     ```
     pip install -r requirements.txt
     ```
   - **Start Command:**
     ```
     python -m server
     ```
   - **Instance Type:** `Free` (spins down after 15 min of inactivity, but re-activates instantly when you connect)

4. **Set Environment Variables** (optional for local testing):
   - Leave empty for now (game will use defaults)

5. **Click Create Web Service** and wait for deployment (2-5 minutes)

## Step 3: Get Your Server URL

Once deployed, Render gives you a URL like:
```
https://toadbusiness-abc123.onrender.com
```

**This is your game server address** that everyone uses to connect.

## Step 4: Connect Players

### For Local Development (on your machine):
1. Open the game in your browser: `http://localhost:8000`
2. In the server address field, enter: `localhost:8000`
3. Click "Connect to Server"

### For Remote Players (on other machines):
1. Send them the **Render URL**: `https://toadbusiness-abc123.onrender.com`
2. They enter it in the server address field when connecting
3. Click "Connect to Server"

**Note:** For Render URLs, the field should accept just the domain without `https://` or `/ws`. The app will add `wss://` automatically for secure WebSocket.

## Common Issues

### "Connection Error" when connecting
- **Check the server address** — Make sure there are no typos
- **Wait for Render boot-up** — If the service is on a free tier, it spins down after 15 minutes. When you first try to connect, Render may take 30 seconds to restart it.
- **Check Render dashboard** — Visit your Web Service dashboard on Render to confirm it's running (green indicator)

### "Disconnected from server"
- Your WebSocket connection was interrupted (rare)
- **Refresh the page** or **click "Connect to Server" again** to reconnect

### Why does it restart sometimes?
- **Free tier behavior** — Render's free tier spins down after 15 minutes of inactivity to save resources
- First connection after spin-down takes ~30 seconds (this is normal)
- Once running, performance is smooth

## Monitoring and Logs

### View Server Logs:
1. Go to [render.com/dashboard](https://render.com/dashboard)
2. Click your `toadbusiness` service
3. Click **Logs** tab to see real-time debug output

### Check Service Status:
- Green indicator = Service is running
- Yellow indicator = Spinning up (30s boot time on free tier)
- Red indicator = Service crashed (check logs)

## Scaling Up (Beyond Free Tier)

If you want to:
- **Remove spin-down** — Upgrade to paid tier (~$5-10/month for small games)
- **Host multiple servers** — Deploy multiple instances for load balancing
- **Use a database** — Add PostgreSQL for persistent data storage

Contact Render support or upgrade your account in the dashboard.

## Development Workflow

### Testing Locally:
```bash
python server.py
# Open http://localhost:8000 in browser
```

### Deploy Changes:
```bash
git add .
git commit -m "Your changes"
git push origin main
# Render auto-deploys within 1-2 minutes
```

### Rollback (if something breaks):
Render keeps recent deployment history. Go to **Dashboard → Deploys** and click "Redeploy" on a previous version.

## File Structure Reference

```
toadbusiness/
├── server.py           # Run this locally OR Render runs it automatically
├── game/
│   ├── app_server.py   # WebSocket server with game logic
│   ├── simulation.py    # Market engine
│   ├── models.py        # Game data classes
│   ├── persistence.py   # Save/load game state
│   ├── catalog.py       # Item definitions
│   └── ...
├── public/
│   ├── app.js           # Client-side game logic (server-only mode)
│   ├── index.html       # Server address input form
│   ├── styles.css       # UI styling
│   └── ...
├── data/
│   └── game_state.json  # Persisted game data
├── requirements.txt     # Python dependencies
└── RENDER_DEPLOYMENT.md # This file
```

## Getting Help

- **Render docs** — https://render.com/docs
- **Game server logs** — Check Render dashboard → Logs tab
- **Local testing** — `python server.py` runs on `http://localhost:8000`

Enjoy Toad Business!
