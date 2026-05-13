const state = {
  socket: null,
  serverAddress: localStorage.getItem("toadBusinessServerAddress") || window.location.host,
  lobbyStatus: "Enter server address and connect.",
  playerName: localStorage.getItem("toadBusinessName") || "",
  playerColor: localStorage.getItem("toadBusinessColor") || "#000080",
  messageColor: localStorage.getItem("toadBusinessMessageColor") || "#111111",
  chatFont: localStorage.getItem("toadBusinessChatFont") || "MS Sans Serif",
  selectedStockId: localStorage.getItem("toadBusinessSelectedStock") || "toad-bean",
  sidebarTab: "stocks",
  mainTab: "holdings",
  rightTab: "chat",
  tickerSignature: "",
  tickerRenderedAt: 0,
  pendingConfirm: null,
  market: null,
  player: null,
  chatLog: [],
  lastNoticeAt: 0,
};

const elements = {
  lobbyDialog: document.querySelector("#lobbyDialog"),
  hostGameBtn: document.querySelector("#hostGameBtn"),
  joinGameBtn: document.querySelector("#joinGameBtn"),
  serverAddressInput: document.querySelector("#serverAddressInput"),
  connectBtn: document.querySelector("#connectBtn"),
  optionsButton: document.querySelector("#optionsButton"),
  optionsDialog: document.querySelector("#optionsDialog"),
  optionsForm: document.querySelector("#optionsForm"),
  optionsName: document.querySelector("#optionsName"),
  optionsNameColor: document.querySelector("#optionsNameColor"),
  optionsMessageColor: document.querySelector("#optionsMessageColor"),
  optionsChatFont: document.querySelector("#optionsChatFont"),
  optionsCancel: document.querySelector("#optionsCancel"),
  playerName: document.querySelector("#playerName"),
  playerColor: document.querySelector("#playerColor"),
  messageColor: document.querySelector("#messageColor"),
  chatFont: document.querySelector("#chatFont"),
  confirmDialog: document.querySelector("#confirmDialog"),
  confirmForm: document.querySelector("#confirmForm"),
  confirmTitle: document.querySelector("#confirmTitle"),
  confirmBody: document.querySelector("#confirmBody"),
  confirmCancel: document.querySelector("#confirmCancel"),
  tickerTrack: document.querySelector("#tickerTrack"),
  onlineCount: document.querySelector("#onlineCount"),
  globalClock: document.querySelector("#globalClock"),
  stockList: document.querySelector("#stockList"),
  moverList: document.querySelector("#moverList"),
  realEstateList: document.querySelector("#realEstateList"),
  businessList: document.querySelector("#businessList"),
  sabotageList: document.querySelector("#sabotageList"),
  stockTitle: document.querySelector("#stockTitle"),
  stockStats: document.querySelector("#stockStats"),
  stockMeta: document.querySelector("#stockMeta"),
  stockChart: document.querySelector("#stockChart"),
  cashValue: document.querySelector("#cashValue"),
  incomeValue: document.querySelector("#incomeValue"),
  upgradeIncomeBtn: document.querySelector("#upgradeIncomeBtn"),
  shareAmount: document.querySelector("#shareAmount"),
  buyBtn: document.querySelector("#buyBtn"),
  sellBtn: document.querySelector("#sellBtn"),
  maxBuyBtn: document.querySelector("#maxBuyBtn"),
  maxSellBtn: document.querySelector("#maxSellBtn"),
  ownedShares: document.querySelector("#ownedShares"),
  noticeArea: document.querySelector("#noticeArea"),
  portfolioSummary: document.querySelector("#portfolioSummary"),
  portfolioTable: document.querySelector("#portfolioTable"),
  chatLog: document.querySelector("#chatLog"),
  chatForm: document.querySelector("#chatForm"),
  chatInput: document.querySelector("#chatInput"),
  leaderboard: document.querySelector("#leaderboard"),
  lobbyPanel: document.querySelector("#lobbyPanel"),
  connectionStatus: document.querySelector("#connectionStatus"),
};

function formatMoney(value) {
  return Number(value || 0).toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function formatPercent(value) {
  const number = Number(value || 0);
  const sign = number > 0 ? "+" : "";
  return `${sign}${number.toFixed(2)}%`;
}

function directionClass(value) {
  if (Number(value) > 0.03) return "positive";
  if (Number(value) < -0.03) return "negative";
  return "flat";
}

function selectedStock() {
  const stocks = state.market?.stocks || [];
  return stocks.find((stock) => stock.id === state.selectedStockId) || stocks[0] || null;
}

function selectedPosition() {
  const stock = selectedStock();
  if (!stock || !state.player) return null;
  return state.player.positions.find((position) => position.stockId === stock.id) || null;
}

function maxBuyShares(stock) {
  if (!stock || !state.player) return 0;
  return Math.max(0, Math.min(Math.floor(Number(state.player.cash) / Number(stock.price)), Number(stock.remainingVolume || 0)));
}

function safeColor(value) {
  return /^#[0-9a-fA-F]{6}$/.test(value || "") ? value : "#000080";
}

function safeMessageColor(value) {
  return /^#[0-9a-fA-F]{6}$/.test(value || "") ? value : "#111111";
}

function safeFont(value) {
  const allowed = ["MS Sans Serif", "Tahoma", "Verdana", "Arial", "Courier New", "Lucida Console", "Terminal", "Consolas"];
  return allowed.includes(value) ? value : "MS Sans Serif";
}

function profilePayload() {
  return {
    name: state.playerName,
    color: state.playerColor,
    messageColor: state.messageColor,
    chatFont: state.chatFont,
  };
}

function saveProfileFromLobby() {
  const name = elements.playerName.value.trim();
  if (!name) {
    showLobbyStatus("Enter a player name first.");
    return false;
  }
  state.playerName = name;
  state.playerColor = safeColor(elements.playerColor.value);
  state.messageColor = safeMessageColor(elements.messageColor.value);
  state.chatFont = safeFont(elements.chatFont.value);
  localStorage.setItem("toadBusinessName", state.playerName);
  localStorage.setItem("toadBusinessColor", state.playerColor);
  localStorage.setItem("toadBusinessMessageColor", state.messageColor);
  localStorage.setItem("toadBusinessChatFont", state.chatFont);
  return true;
}

function connectServer() {
  if (!saveProfileFromLobby()) return;
  
  const serverAddr = (elements.serverAddressInput?.value || state.serverAddress).trim();
  if (!serverAddr) {
    showLobbyStatus("Enter a server address.");
    return;
  }
  
  state.serverAddress = serverAddr;
  localStorage.setItem("toadBusinessServerAddress", serverAddr);
  
  const protocol = serverAddr.includes("://") ? "" : (window.location.protocol === "https:" ? "wss:" : "ws:");
  const url = protocol ? `${protocol}//${serverAddr}/ws` : `${serverAddr}/ws`;
  
  const socket = new WebSocket(url);
  state.socket = socket;
  elements.connectionStatus.textContent = "Connecting";

  socket.addEventListener("open", () => {
    elements.connectionStatus.textContent = "Connected";
    showLobbyStatus("Connected to server.");
    if (state.playerName) {
      sendToServerSocket(socket, { type: "join", ...profilePayload() });
    }
  });

  socket.addEventListener("close", () => {
    elements.connectionStatus.textContent = "Disconnected";
    showLobbyStatus("Disconnected from server. Click Connect to retry.");
  });

  socket.addEventListener("error", (event) => {
    elements.connectionStatus.textContent = "Connection Error";
    showLobbyStatus("Failed to connect to server. Check the address and try again.", true);
  });

  socket.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    handleMessage(message);
  });
}

function send(payload) {
  sendToServerSocket(state.socket, payload);
}

function sendToServerSocket(socket, payload) {
  if (socket?.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(payload));
  }
}

function handleMessage(message) {
  if (message.type === "welcome") {
    state.player = message.player;
    state.market = message.market;
    state.chatLog = message.chatLog || [];
    elements.lobbyDialog.classList.add("hidden");
    renderAll();
    return;
  }
  if (message.type === "snapshot") {
    state.market = message.market;
    if (message.player) state.player = message.player;
    renderAll();
    return;
  }
  if (message.type === "player") {
    state.player = message.player;
    renderPlayer();
    return;
  }
  if (message.type === "chat") {
    state.chatLog.push(message.entry);
    state.chatLog = state.chatLog.slice(-60);
    renderChat();
    return;
  }
  if (message.type === "notice" || message.type === "error") {
    showNotice(message.message, message.type === "error");
  }
}

function renderAll() {
  renderMarket();
  renderSelectedStock();
  renderPlayer();
  renderTicker();
  renderChat();
  renderLeaderboard();
  renderLobbyPanel();
  renderRightTab();
}

function renderMarket() {
  const stocks = state.market?.stocks || [];
  elements.onlineCount.textContent = state.market?.connectedPlayers || 0;
  elements.globalClock.textContent = state.market?.globalTime?.replace(" UTC", "") || "--:--:--";

  const tabMap = {
    stocks: elements.stockList,
    movers: elements.moverList,
    realEstate: elements.realEstateList,
    businesses: elements.businessList,
    sabotage: elements.sabotageList,
  };
  Object.entries(tabMap).forEach(([tab, element]) => {
    element.classList.toggle("hidden", state.sidebarTab !== tab);
  });

  elements.stockList.innerHTML = stocks.map(stockRowMarkup).join("");
  renderMovers();
  renderRealEstateMarket();
  renderBusinessMarket();
  renderSabotageMarket();
}

function stockRowMarkup(stock) {
  const selected = stock.id === selectedStock()?.id ? "active" : "";
  const trend = directionClass(stock.percentChange);
  return `
    <button class="stock-row ${selected}" data-stock-id="${escapeHtml(stock.id)}">
      <strong>${escapeHtml(stock.name)}</strong>
      <span class="${trend}">${formatPercent(stock.percentChange)}</span>
      <small>${escapeHtml(stock.symbol)} ${formatMoney(stock.price)} | ${escapeHtml(stock.volatilityLabel)} vol</small>
    </button>
  `;
}

function renderMovers() {
  const gainers = state.market?.movers?.gainers || [];
  const losers = state.market?.movers?.losers || [];
  elements.moverList.innerHTML = `
    <div class="mover-row"><strong>Rising</strong><span></span></div>
    ${gainers.map((stock) => moverMarkup(stock)).join("")}
    <div class="mover-row"><strong>Falling</strong><span></span></div>
    ${losers.map((stock) => moverMarkup(stock)).join("")}
  `;
}

function moverMarkup(stock) {
  return `
    <button class="mover-row" data-stock-id="${escapeHtml(stock.id)}">
      <span>${escapeHtml(stock.symbol)}</span>
      <strong class="${directionClass(stock.percentChange)}">${formatPercent(stock.percentChange)}</strong>
    </button>
  `;
}

function renderRealEstateMarket() {
  const catalog = state.market?.realEstateCatalog || [];
  const owned = state.player?.realEstate || [];
  const catalogMarkup = catalog
    .map((asset) => `
      <div class="asset-card">
        <strong>${escapeHtml(asset.name)}</strong>
        <span>${formatMoney(asset.cost)} | rent ${formatMoney(asset.base_rent)}/hr</span>
        <button data-action="buy-property" data-template-id="${escapeHtml(asset.id)}">Buy</button>
      </div>
    `)
    .join("");
  const ownedMarkup = owned
    .map((asset) => `
      <div class="asset-card owned">
        <strong>${escapeHtml(asset.name)} L${asset.level}</strong>
        <span>Value ${formatMoney(asset.value)} | Income ${formatMoney(asset.incomePerHour)}/hr</span>
        <span>Tenant: ${asset.renter ? `${escapeHtml(asset.renter.name)} (${escapeHtml(asset.renter.quality)})` : "Vacant"}</span>
        <div class="mini-actions">
          <button data-action="upgrade-property" data-asset-id="${escapeHtml(asset.id)}">Upgrade</button>
          <button data-action="set-rent" data-asset-id="${escapeHtml(asset.id)}">Rent</button>
          <button data-action="evict-renter" data-asset-id="${escapeHtml(asset.id)}">Evict</button>
          <button data-action="sell-property" data-asset-id="${escapeHtml(asset.id)}">Sell</button>
        </div>
      </div>
    `)
    .join("");
  elements.realEstateList.innerHTML = `<div class="asset-section-title">Buy Property</div>${catalogMarkup}<div class="asset-section-title">Owned</div>${ownedMarkup || emptySmall("No properties yet")}`;
}

function renderBusinessMarket() {
  const catalog = state.market?.businessCatalog || [];
  const owned = state.player?.businesses || [];
  const catalogMarkup = catalog
    .map((asset) => `
      <div class="asset-card">
        <strong>${escapeHtml(asset.name)}</strong>
        <span>${formatMoney(asset.cost)} | income ${formatMoney(asset.income_per_hour)}/hr</span>
        <button data-action="buy-business" data-template-id="${escapeHtml(asset.id)}">Buy</button>
      </div>
    `)
    .join("");
  const ownedMarkup = owned
    .map((asset) => `
      <div class="asset-card owned">
        <strong>${escapeHtml(asset.name)} L${asset.level}</strong>
        <span>Value ${formatMoney(asset.value)} | Income ${formatMoney(asset.incomePerHour)}/hr</span>
        <span>Stock ${formatMoney(asset.stockPrice)}</span>
        <div class="mini-actions">
          <button data-action="upgrade-business" data-business-id="${escapeHtml(asset.id)}">Upgrade</button>
          <button data-action="rename-business" data-business-id="${escapeHtml(asset.id)}">Rename</button>
          <button data-action="select-stock" data-stock-id="${escapeHtml(asset.stockId)}">Stock</button>
          <button data-action="sell-business" data-business-id="${escapeHtml(asset.id)}">Sell</button>
        </div>
      </div>
    `)
    .join("");
  elements.businessList.innerHTML = `<div class="asset-section-title">Buy Business</div>${catalogMarkup}<div class="asset-section-title">Owned</div>${ownedMarkup || emptySmall("No businesses yet")}`;
}

function renderSabotageMarket() {
  const stock = selectedStock();
  const options = state.market?.sabotageOptions || [];
  if (!stock) {
    elements.sabotageList.innerHTML = emptySmall("Select a stock first");
    return;
  }
  const cooldowns = state.player?.sabotageCooldowns || {};
  elements.sabotageList.innerHTML = `
    <div class="asset-section-title">Target: ${escapeHtml(stock.name)}</div>
    ${options.map((option) => {
      const cost = option.costByStock?.[stock.id] || option.base_cost || 0;
      const cooldown = Number(cooldowns[option.id] || 0);
      return `
        <div class="asset-card">
          <strong>${escapeHtml(option.name)}</strong>
          <span>${escapeHtml(option.description)}</span>
          <span>Cost ${formatMoney(cost)}${cooldown > 0 ? ` | Cooldown ${cooldown}s` : ""}</span>
          <button data-action="sabotage" data-option-id="${escapeHtml(option.id)}" ${cooldown > 0 ? "disabled" : ""}>Fund</button>
        </div>
      `;
    }).join("")}
  `;
}

function emptySmall(text) {
  return `<div class="empty-small">${escapeHtml(text)}</div>`;
}

function renderTicker() {
  const ticker = state.market?.ticker || [];
  const news = state.market?.news || [];
  if (!ticker.length && !news.length) {
    elements.tickerTrack.textContent = "Waiting for market data";
    return;
  }
  const signature = [
    ...news.slice(0, 6).map((item) => `${item.ts}:${item.title}`),
    ...ticker.slice(0, 8).map((stock) => `${stock.id}:${stock.percentChange}:${stock.price}`),
  ].join("|");
  const now = Date.now();
  if (signature === state.tickerSignature || now - state.tickerRenderedAt < 4500) {
    return;
  }
  state.tickerSignature = signature;
  state.tickerRenderedAt = now;
  const newsItems = news.slice(0, 8).map((item) => {
    const tag = item.severity === "major" ? "major-news" : "normal-news";
    return `<span class="${tag}"><strong>${escapeHtml(item.title)}</strong> ${escapeHtml(item.body || "")}</span>`;
  });
  const stockItems = ticker.map((stock) => {
    const trend = directionClass(stock.percentChange);
    return `<span><strong>${escapeHtml(stock.name)}</strong> ${formatMoney(stock.price)} <b class="${trend}">${formatPercent(stock.percentChange)}</b></span>`;
  });
  elements.tickerTrack.innerHTML = newsItems.concat(stockItems, newsItems, stockItems).join("");
}

function renderSelectedStock() {
  const stock = selectedStock();
  if (!stock) return;
  localStorage.setItem("toadBusinessSelectedStock", stock.id);
  elements.stockTitle.textContent = `${stock.name} (${stock.symbol})`;
  const trend = directionClass(stock.percentChange);
  elements.stockStats.innerHTML = [
    statMarkup("Price", formatMoney(stock.price), trend),
    statMarkup("Move", formatPercent(stock.percentChange), trend),
    statMarkup("Owned", `${selectedPosition()?.shares || 0}`, ""),
    statMarkup("Available", stock.remainingVolume.toLocaleString(), ""),
  ].join("");
  elements.stockMeta.innerHTML = [
    statMarkup("Sector", stock.sector, ""),
    statMarkup("CEO", stock.ceo, ""),
    statMarkup("Volatility", stock.volatilityLabel, ""),
    statMarkup("Beta", stock.beta.toFixed(2), ""),
    statMarkup("Moon", stock.moonSensitive ? state.market?.moonPhase || "Tracking" : "No", ""),
    statMarkup("Held", stock.heldByPlayers.toLocaleString(), ""),
    statMarkup("Day Volume", stock.dayVolume.toLocaleString(), ""),
    statMarkup("Quip", stock.quip || "No news", ""),
  ].join("");
  elements.ownedShares.textContent = `${selectedPosition()?.shares || 0} shares`;
  drawChart(stock);
}

function statMarkup(label, value, className) {
  return `
    <div class="stat-box">
      <span class="muted">${escapeHtml(label)}</span>
      <strong class="${className}">${escapeHtml(value)}</strong>
    </div>
  `;
}

function drawChart(stock) {
  const canvas = elements.stockChart;
  const wrap = canvas.parentElement;
  const dpr = window.devicePixelRatio || 1;
  const rect = wrap.getBoundingClientRect();
  const width = Math.max(320, Math.min(1400, Math.floor(rect.width || wrap.clientWidth || 320)));
  const height = Math.max(220, Math.min(720, Math.floor(rect.height || wrap.clientHeight || 220)));
  canvas.width = Math.floor(width * dpr);
  canvas.height = Math.floor(height * dpr);

  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#f9f9f9";
  ctx.fillRect(0, 0, width, height);

  const padding = { left: 54, right: 26, top: 18, bottom: 32 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const history = (stock.history || []).slice(-240);
  const prices = history.map((point) => Number(point.price));
  const minPrice = Math.min(...prices, stock.price);
  const maxPrice = Math.max(...prices, stock.price);
  const spread = Math.max(0.1, maxPrice - minPrice);
  const low = minPrice - spread * 0.08;
  const high = maxPrice + spread * 0.08;

  ctx.strokeStyle = "#d0d0d0";
  ctx.lineWidth = 1;
  ctx.font = "12px Tahoma, sans-serif";
  ctx.fillStyle = "#333";
  for (let i = 0; i <= 4; i += 1) {
    const y = padding.top + (plotHeight / 4) * i;
    ctx.beginPath();
    ctx.moveTo(padding.left, y);
    ctx.lineTo(width - padding.right, y);
    ctx.stroke();
    const value = high - ((high - low) / 4) * i;
    ctx.fillText(formatMoney(value), 6, y + 4);
  }

  ctx.strokeStyle = "#808080";
  ctx.strokeRect(padding.left, padding.top, plotWidth, plotHeight);

  if (history.length < 2) {
    ctx.fillText("Waiting for ticks", padding.left + 12, padding.top + 24);
    return;
  }

  const newestTs = Number(history[history.length - 1].ts);
  const oldestTs = Number(history[0].ts);
  const windowSeconds = Math.max(30, newestTs - oldestTs);
  const lineColor = stock.percentChange >= 0 ? "#107c10" : "#b00020";
  ctx.strokeStyle = lineColor;
  ctx.lineWidth = 2;
  ctx.beginPath();
  history.forEach((point, index) => {
    const age = newestTs - Number(point.ts);
    const x = width - padding.right - (age / windowSeconds) * plotWidth;
    const y = padding.top + plotHeight - ((Number(point.price) - low) / (high - low)) * plotHeight;
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();

  const lastX = width - padding.right;
  const lastY = padding.top + plotHeight - ((Number(stock.price) - low) / (high - low)) * plotHeight;
  ctx.fillStyle = lineColor;
  ctx.beginPath();
  ctx.arc(lastX, lastY, 5, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#111";
  ctx.fillText("now", lastX - 18, Math.max(14, lastY - 10));
}

function renderPlayer() {
  const player = state.player;
  if (!player) return;
  elements.cashValue.textContent = formatMoney(player.cash);
  elements.incomeValue.textContent = `${formatMoney(player.totalHourlyIncome || player.hourlyIncome)}/hr`;
  elements.upgradeIncomeBtn.textContent = `Upgrade Wage (${formatMoney(player.nextIncomeUpgradeCost)})`;
  elements.upgradeIncomeBtn.disabled = Number(player.cash) < Number(player.nextIncomeUpgradeCost);
  renderSelectedStock();
  renderPortfolio();
}

function renderPortfolio() {
  const player = state.player;
  if (!player) return;
  const portfolio = player.portfolio;
  elements.portfolioSummary.innerHTML = [
    statMarkup("Net Worth", formatMoney(portfolio.netWorth), ""),
    statMarkup("Stocks", formatMoney(portfolio.marketValue), ""),
    statMarkup("Property", formatMoney(portfolio.propertyValue), ""),
    statMarkup("Business", formatMoney(portfolio.businessValue), ""),
  ].join("");

  if (state.mainTab === "risk") {
    renderRiskTable(player);
    return;
  }

  if (!player.positions.length) {
    elements.portfolioTable.innerHTML = `<div class="portfolio-row"><span>No holdings yet</span><span></span><span></span></div>`;
    return;
  }

  const rows = player.positions
    .map((position) => {
      const pnlClass = directionClass(position.unrealizedPnl);
      return `
        <div class="portfolio-row">
          <span><strong>${escapeHtml(position.symbol)}</strong> ${escapeHtml(position.name)}</span>
          <span>${position.shares}</span>
          <span>${formatMoney(position.marketValue)}</span>
          <span>${formatMoney(position.averageCost)}</span>
          <span class="${pnlClass}">${formatMoney(position.unrealizedPnl)}</span>
          <span>${escapeHtml(position.riskLabel)}</span>
        </div>
      `;
    })
    .join("");
  elements.portfolioTable.innerHTML = `
    <div class="portfolio-row header">
      <span>Stock</span><span>Shares</span><span>Value</span><span>Avg</span><span>P/L</span><span>Risk</span>
    </div>
    ${rows}
  `;
}

function renderRiskTable(player) {
  const rows = player.positions
    .map((position) => {
      const pnlClass = directionClass(position.unrealizedPnl + position.realizedPnl);
      return `
        <div class="portfolio-row">
          <span><strong>${escapeHtml(position.symbol)}</strong> ${escapeHtml(position.name)}</span>
          <span>${escapeHtml(position.riskLabel)}</span>
          <span>${position.riskScore.toFixed(1)}</span>
          <span>${formatMoney(position.marketValue)}</span>
          <span class="${pnlClass}">${formatMoney(position.unrealizedPnl + position.realizedPnl)}</span>
          <span>${formatMoney(position.realizedPnl)}</span>
        </div>
      `;
    })
    .join("");
  elements.portfolioTable.innerHTML = rows
    ? `<div class="portfolio-row header"><span>Stock</span><span>Risk</span><span>Score</span><span>Value</span><span>Total P/L</span><span>Realized</span></div>${rows}`
    : `<div class="portfolio-row"><span>No risk yet</span><span></span><span></span></div>`;
}

function renderChat() {
  elements.chatLog.innerHTML = state.chatLog
    .map((entry) => {
      const date = new Date(entry.ts * 1000);
      const time = date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      const nameColor = safeColor(entry.color);
      const messageColor = safeMessageColor(entry.messageColor || entry.color);
      const chatFont = safeFont(entry.chatFont);
      return `<div class="chat-line" style="color:${messageColor};font-family:'${chatFont}', Tahoma, sans-serif"><strong style="color:${nameColor}">${escapeHtml(entry.name)}</strong> <span class="muted">${time}</span><br>${escapeHtml(entry.message)}</div>`;
    })
    .join("");
  elements.chatLog.scrollTop = elements.chatLog.scrollHeight;
}

function renderLeaderboard() {
  const rows = state.market?.leaderboard || [];
  elements.leaderboard.innerHTML = rows
    .map((row, index) => `
      <div class="leader-row">
        <strong>${index + 1}. <span style="color:${safeColor(row.color)}">${escapeHtml(row.name)}</span></strong>
        <span>${formatMoney(row.netWorth)} ${row.online ? "online" : "offline"}</span>
      </div>
    `)
    .join("") || emptySmall("No players yet");
}

function renderLobbyPanel() {
  const status = state.socket?.readyState === WebSocket.OPEN ? "Connected" : state.socket?.readyState === WebSocket.CONNECTING ? "Connecting" : "Disconnected";
  const playerCount = state.market?.connectedPlayers || 0;
  elements.lobbyPanel.innerHTML = `
    <div class="asset-section-title">Connection</div>
    <div class="leader-row"><strong>Status</strong><span>${escapeHtml(status)}</span></div>
    <div class="leader-row"><strong>Server</strong><span>${escapeHtml(state.serverAddress)}</span></div>
    <div class="leader-row"><strong>Players Online</strong><span>${playerCount}</span></div>
    <div class="lobby-warning">All players connect to a single game server. The server hosts the simulation and persists game state. For local development, use the default server address. For production on Render, deploy this app and use your Render URL.</div>
  `;
}

function renderRightTab() {
  const showChat = state.rightTab === "chat";
  elements.chatLog.classList.toggle("hidden", !showChat);
  elements.chatForm.classList.toggle("hidden", !showChat);
  elements.leaderboard.classList.toggle("hidden", state.rightTab !== "leaderboard");
  elements.lobbyPanel.classList.toggle("hidden", state.rightTab !== "lobby");
}

function showNotice(message, isError = false) {
  state.lastNoticeAt = Date.now();
  const className = isError ? "negative" : "positive";
  elements.noticeArea.innerHTML = `<strong class="${className}">${escapeHtml(message)}</strong>`;
}

function showLobbyStatus(message, isError = false) {
  state.lobbyStatus = message;
  if (elements.noticeArea) {
    elements.noticeArea.innerHTML = `<strong${isError ? ' class="negative"' : ""}>${escapeHtml(message)}</strong>`;
  }
  renderLobbyPanel();
}


function showConfirm(title, rows, payload) {
  state.pendingConfirm = payload;
  elements.confirmTitle.textContent = title;
  elements.confirmBody.innerHTML = rows.map(([label, value, className = ""]) => `
    <div class="confirm-row"><span>${escapeHtml(label)}</span><strong class="${className}">${escapeHtml(value)}</strong></div>
  `).join("");
  elements.confirmDialog.classList.remove("hidden");
}

function estimateImpact(stock, shares) {
  const volumeRatio = shares / Math.max(stock.maxVolume || 1, 1);
  return Math.min(0.18, volumeRatio * (0.9 + stock.volatility) / Math.max(stock.liquidity, 0.1) * 3.4) * 100;
}

function confirmTrade(type, shares) {
  const stock = selectedStock();
  if (!stock || shares <= 0) return;
  const side = type === "buy" || type === "buyMax" ? "buy" : "sell";
  const cost = Number(stock.price) * shares;
  const impact = estimateImpact(stock, shares) * (side === "sell" ? -1 : 1);
  showConfirm(
    side === "buy" ? "Confirm Purchase" : "Confirm Sale",
    [
      ["Stock", `${stock.name} (${stock.symbol})`],
      ["Shares", shares.toLocaleString()],
      [side === "buy" ? "Cost" : "Proceeds", formatMoney(cost)],
      ["Estimated Price Impact", formatPercent(impact), directionClass(impact)],
    ],
    { type, stockId: stock.id, shares },
  );
}

function trade(type) {
  const stock = selectedStock();
  if (!stock) return;
  let shares = Math.floor(Number(elements.shareAmount.value || 0));
  if (type === "buyMax") shares = maxBuyShares(stock);
  if (type === "sellMax") shares = selectedPosition()?.shares || 0;
  confirmTrade(type, shares);
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => {
    const entities = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;",
    };
    return entities[char];
  });
}

document.addEventListener("click", (event) => {
  const stockButton = event.target.closest("[data-stock-id]");
  if (stockButton && !event.target.closest("[data-action]")) {
    state.selectedStockId = stockButton.dataset.stockId;
    renderAll();
    return;
  }

  const sidebarTab = event.target.closest("[data-sidebar-tab]");
  if (sidebarTab) {
    state.sidebarTab = sidebarTab.dataset.sidebarTab;
    document.querySelectorAll("[data-sidebar-tab]").forEach((button) => {
      button.classList.toggle("active", button.dataset.sidebarTab === state.sidebarTab);
    });
    renderMarket();
    return;
  }

  const mainTab = event.target.closest("[data-main-tab]");
  if (mainTab) {
    state.mainTab = mainTab.dataset.mainTab;
    document.querySelectorAll("[data-main-tab]").forEach((button) => {
      button.classList.toggle("active", button.dataset.mainTab === state.mainTab);
    });
    renderPortfolio();
    return;
  }

  const rightTab = event.target.closest("[data-right-tab]");
  if (rightTab) {
    state.rightTab = rightTab.dataset.rightTab;
    document.querySelectorAll("[data-right-tab]").forEach((button) => {
      button.classList.toggle("active", button.dataset.rightTab === state.rightTab);
    });
    renderRightTab();
    return;
  }

  const actionButton = event.target.closest("[data-action]");
  if (actionButton) {
    handleAction(actionButton);
  }
});

function handleAction(button) {
  const action = button.dataset.action;
  if (action === "refresh-lobby-code") {
    requestHostLobbyCode().catch((error) => showLobbyStatus(error.message));
    return;
  }
  if (action === "copy-lobby-code") {
    const link = `${window.location.origin}${window.location.pathname}#lobby=${encodeURIComponent(state.lobbyCode)}`;
    navigator.clipboard?.writeText(link);
    showLobbyStatus("Lobby invite link copied.");
    return;
  }
  if (action === "select-stock") {
    state.selectedStockId = button.dataset.stockId;
    state.sidebarTab = "stocks";
    renderAll();
    return;
  }
  if (action === "buy-property") {
    const template = (state.market?.realEstateCatalog || []).find((item) => item.id === button.dataset.templateId);
    showConfirm("Confirm Property Purchase", [["Property", template?.name || ""], ["Cost", formatMoney(template?.cost || 0)], ["Rent", `${formatMoney(template?.base_rent || 0)}/hr`]], { type: "buyProperty", templateId: button.dataset.templateId });
    return;
  }
  if (action === "sell-property") {
    const asset = (state.player?.realEstate || []).find((item) => item.id === button.dataset.assetId);
    showConfirm("Confirm Property Sale", [["Property", asset?.name || ""], ["Sale Value", formatMoney(asset?.value || 0)]], { type: "sellProperty", assetId: button.dataset.assetId });
    return;
  }
  if (action === "upgrade-property") {
    const asset = (state.player?.realEstate || []).find((item) => item.id === button.dataset.assetId);
    showConfirm("Confirm Property Upgrade", [["Property", asset?.name || ""], ["Cost", formatMoney(asset?.upgradeCost || 0)]], { type: "upgradeProperty", assetId: button.dataset.assetId });
    return;
  }
  if (action === "evict-renter") {
    showConfirm("Confirm Eviction", [["Action", "Replace current renter"], ["Result", "New renter is random"]], { type: "evictRenter", assetId: button.dataset.assetId });
    return;
  }
  if (action === "set-rent") {
    const asset = (state.player?.realEstate || []).find((item) => item.id === button.dataset.assetId);
    const value = window.prompt("Rent per hour", asset?.rentPerHour || 10);
    if (value) send({ type: "setRent", assetId: button.dataset.assetId, rentPerHour: Number(value) });
    return;
  }
  if (action === "buy-business") {
    const template = (state.market?.businessCatalog || []).find((item) => item.id === button.dataset.templateId);
    showConfirm("Confirm Business Purchase", [["Business", template?.name || ""], ["Cost", formatMoney(template?.cost || 0)], ["Income", `${formatMoney(template?.income_per_hour || 0)}/hr`]], { type: "buyBusiness", templateId: button.dataset.templateId });
    return;
  }
  if (action === "sell-business") {
    const asset = (state.player?.businesses || []).find((item) => item.id === button.dataset.businessId);
    showConfirm("Confirm Business Sale", [["Business", asset?.name || ""], ["Sale Value", formatMoney(asset?.value || 0)]], { type: "sellBusiness", businessId: button.dataset.businessId });
    return;
  }
  if (action === "upgrade-business") {
    const asset = (state.player?.businesses || []).find((item) => item.id === button.dataset.businessId);
    showConfirm("Confirm Business Upgrade", [["Business", asset?.name || ""], ["Cost", formatMoney(asset?.upgradeCost || 0)]], { type: "upgradeBusiness", businessId: button.dataset.businessId });
    return;
  }
  if (action === "rename-business") {
    const asset = (state.player?.businesses || []).find((item) => item.id === button.dataset.businessId);
    const name = window.prompt("Business name", asset?.name || "");
    if (name) send({ type: "renameBusiness", businessId: button.dataset.businessId, name });
    return;
  }
  if (action === "sabotage") {
    const stock = selectedStock();
    const option = (state.market?.sabotageOptions || []).find((item) => item.id === button.dataset.optionId);
    const cost = option?.costByStock?.[stock?.id] || option?.base_cost || 0;
    showConfirm(
      "Confirm Sabotage Influence",
      [
        ["Target", stock?.name || ""],
        ["Method", option?.name || ""],
        ["Cost", formatMoney(cost)],
        ["Outcome", "Raises odds only"],
      ],
      { type: "sabotage", stockId: stock?.id, optionId: button.dataset.optionId },
    );
  }
}

// Button event listeners
elements.hostGameBtn?.addEventListener("click", () => {
  connectServer();
});

elements.joinGameBtn?.addEventListener("click", () => {
  connectServer();
});

elements.connectBtn?.addEventListener("click", () => {
  connectServer();
});

elements.optionsButton.addEventListener("click", () => {
  elements.optionsName.value = state.playerName;
  elements.optionsNameColor.value = safeColor(state.playerColor);
  elements.optionsMessageColor.value = safeMessageColor(state.messageColor);
  elements.optionsChatFont.value = safeFont(state.chatFont);
  elements.optionsDialog.classList.remove("hidden");
});

elements.optionsCancel.addEventListener("click", () => {
  elements.optionsDialog.classList.add("hidden");
});

elements.optionsForm.addEventListener("submit", (event) => {
  event.preventDefault();
  state.playerName = elements.optionsName.value.trim() || state.playerName;
  state.playerColor = safeColor(elements.optionsNameColor.value);
  state.messageColor = safeMessageColor(elements.optionsMessageColor.value);
  state.chatFont = safeFont(elements.optionsChatFont.value);
  elements.playerName.value = state.playerName;
  elements.playerColor.value = state.playerColor;
  elements.messageColor.value = state.messageColor;
  elements.chatFont.value = state.chatFont;
  localStorage.setItem("toadBusinessName", state.playerName);
  localStorage.setItem("toadBusinessColor", state.playerColor);
  localStorage.setItem("toadBusinessMessageColor", state.messageColor);
  localStorage.setItem("toadBusinessChatFont", state.chatFont);
  if (state.socket?.readyState === WebSocket.OPEN) {
    send({ type: "profile", ...profilePayload() });
  }
  elements.optionsDialog.classList.add("hidden");
});

elements.confirmForm.addEventListener("submit", (event) => {
  event.preventDefault();
  if (state.pendingConfirm) send(state.pendingConfirm);
  state.pendingConfirm = null;
  elements.confirmDialog.classList.add("hidden");
});

elements.confirmCancel.addEventListener("click", () => {
  state.pendingConfirm = null;
  elements.confirmDialog.classList.add("hidden");
});

elements.buyBtn.addEventListener("click", () => trade("buy"));
elements.sellBtn.addEventListener("click", () => trade("sell"));
elements.maxBuyBtn.addEventListener("click", () => trade("buyMax"));
elements.maxSellBtn.addEventListener("click", () => trade("sellMax"));
elements.upgradeIncomeBtn.addEventListener("click", () => send({ type: "upgradeIncome" }));

elements.chatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const message = elements.chatInput.value.trim();
  if (!message) return;
  elements.chatInput.value = "";
  send({ type: "chat", message });
});

window.addEventListener("resize", () => {
  const stock = selectedStock();
  if (stock) drawChart(stock);
});

// Initialize UI
elements.playerName.value = state.playerName;
elements.playerColor.value = safeColor(state.playerColor);
elements.messageColor.value = safeMessageColor(state.messageColor);
elements.chatFont.value = safeFont(state.chatFont);
if (elements.serverAddressInput) {
  elements.serverAddressInput.value = state.serverAddress;
}
