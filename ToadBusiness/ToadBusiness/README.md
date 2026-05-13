# Toad Business

Realtime HTML5 stock trading game prototype with a Python standard-library backend and server-based multiplayer.

## Quick Start (Local Development)

```bash
python server.py --port 8000
```

Open `http://127.0.0.1:8000` in your browser.

**For local testing:**
- Enter player name and customize colors/font
- Server address: `localhost:8000`
- Click "Connect to Server"
- All connected players see the same market in real-time

## Multiplayer Architecture

**Toad Business now uses a centralized server model** (no more P2P):

- **Single server** hosts the game simulation and all player data
- **All players connect** directly to the server via WebSocket
- **Works from anywhere** — no local network limitations, no port forwarding needed
- **Better security** — host IP is never exposed to other players
- **Easy to scale** — just deploy the server to a cloud provider

### For Production Deployment

Deploy to **Render** (free tier) or any cloud hosting:

```bash
# See RENDER_DEPLOYMENT.md for step-by-step instructions
```

Players connect by entering the server URL (e.g., `toadbusiness-xyz.onrender.com`) in the connection dialog.

## Server Options

**Local network only:**
```bash
python server.py --host 127.0.0.1 --port 8000
```

**LAN accessible:**
```bash
python server.py --host 0.0.0.0 --port 8000
```
(Server prints both local and LAN URLs)

**Custom port:**
```bash
python server.py --port 9000
```

## Data Persistence

Player cash, online income, holdings, assets, stock prices, chat history, and news are automatically saved to `data/game_state.json`.

## Game Systems

- **`game/catalog.py`** — Stock definitions with realistic market factors
- **`game/assets.py`** — Real estate, businesses, renters, CEOs, sabotage options
- **`game/simulation.py`** — Market ticks, income calculation, trading logic, portfolio math
- **`game/persistence.py`** — Game state save/load to JSON
- **`game/app_server.py`** — WebSocket server with multiplayer coordination
- **`game/websocket.py`** — Low-level WebSocket protocol implementation
- **`public/app.js`** — Client-side game logic and Windows 98-style UI
- **`public/index.html`** — Connection dialog with server address input

## Deployment

See **[RENDER_DEPLOYMENT.md](./RENDER_DEPLOYMENT.md)** for a complete guide to deploying to Render (free tier supported).
