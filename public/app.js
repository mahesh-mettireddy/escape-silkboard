(() => {
  let currentState = null;
  let stateSignature = "";
  let landmarks = [];
  let totalAirportKm = 38.0;
  let hasServerKey = false;

  const els = {
    clockValue: document.getElementById("clockValue"),
    clockDelta: document.getElementById("clockDelta"),
    minsLeftText: document.getElementById("minsLeftText"),
    battValue: document.getElementById("battValue"),
    battDelta: document.getElementById("battDelta"),
    battFill: document.getElementById("battFill"),
    upiPill: document.getElementById("upiPill"),
    cashValue: document.getElementById("cashValue"),
    cashDelta: document.getElementById("cashDelta"),
    bagValue: document.getElementById("bagValue"),
    bagCount: document.getElementById("bagCount"),
    modeSubText: document.getElementById("modeSubText"),
    weatherBadge: document.getElementById("weatherBadge"),
    kmProgressPill: document.getElementById("kmProgressPill"),
    kmDeltaBadge: document.getElementById("kmDeltaBadge"),
    sceneContextText: document.getElementById("sceneContextText"),
    currentLocBanner: document.getElementById("currentLocBanner"),
    turnBadge: document.getElementById("turnBadge"),
    modelTag: document.getElementById("modelTag"),
    apiAlertBanner: document.getElementById("apiAlertBanner"),
    apiAlertIcon: document.getElementById("apiAlertIcon"),
    apiAlertMessage: document.getElementById("apiAlertMessage"),
    apiAlertActionBtn: document.getElementById("apiAlertActionBtn"),
    storyFeed: document.getElementById("storyFeed"),
    turnForm: document.getElementById("turnForm"),
    commandInput: document.getElementById("commandInput"),
    sendMoveBtn: document.getElementById("sendMoveBtn"),
    sendBtnText: document.getElementById("sendBtnText"),
    tokenBadgeBtn: document.getElementById("tokenBadgeBtn"),
    tokenShortText: document.getElementById("tokenShortText"),
    tokenPopover: document.getElementById("tokenPopover"),
    tpValidationBadge: document.getElementById("tpValidationBadge"),
    tpLastTurn: document.getElementById("tpLastTurn"),
    tpRunTotal: document.getElementById("tpRunTotal"),
    tpRunCost: document.getElementById("tpRunCost"),
    tpKeySource: document.getElementById("tpKeySource"),
    roadBase: document.getElementById("roadBase"),
    roadFill: document.getElementById("roadFill"),
    landmarksLayer: document.getElementById("landmarksLayer"),
    playerVehicle: document.getElementById("playerVehicle"),
    hudClockCard: document.getElementById("hudClockCard"),
    hudBattCard: document.getElementById("hudBattCard"),
    endModal: document.getElementById("endModal"),
    endBadge: document.getElementById("endBadge"),
    endTitle: document.getElementById("endTitle"),
    endReasonText: document.getElementById("endReasonText"),
    finalClockStat: document.getElementById("finalClockStat"),
    finalBattStat: document.getElementById("finalBattStat"),
    finalCashStat: document.getElementById("finalCashStat"),
    finalCostStat: document.getElementById("finalCostStat"),
    playAgainModalBtn: document.getElementById("playAgainModalBtn"),
    newGameBtn: document.getElementById("newGameBtn"),
    themeToggleBtn: document.getElementById("themeToggleBtn"),
    themeIcon: document.getElementById("themeIcon"),
    apiKeyBtn: document.getElementById("apiKeyBtn"),
    keyStatusText: document.getElementById("keyStatusText"),
    apiKeyModal: document.getElementById("apiKeyModal"),
    apiKeyInput: document.getElementById("apiKeyInput"),
    saveApiKeyBtn: document.getElementById("saveApiKeyBtn"),
    closeApiModalBtn: document.getElementById("closeApiModalBtn"),
  };

  function getSavedApiKey() {
    return localStorage.getItem("esc_gemini_api_key") || "";
  }

  function updateApiKeyStatus(meta = null) {
    const userKey = getSavedApiKey();

    if (userKey) {
      els.keyStatusText.textContent = "User Key ✓";
      els.tpKeySource.textContent = "Browser Key";
    } else if (hasServerKey) {
      els.keyStatusText.textContent = "Server Key ✓";
      els.tpKeySource.textContent = "Server .env";
    } else {
      els.keyStatusText.textContent = "No Key";
      els.tpKeySource.textContent = "No Key Set";
    }

    // Two-way Banner Logic:
    // 1. If server or user key ran out of tokens / invalid -> Show sarcastic top alert
    if (meta && (meta.api_status === "quota_exhausted" || meta.api_status === "invalid_key")) {
      els.apiAlertBanner.style.display = "flex";
      els.apiAlertBanner.className = "api-alert-banner quota-error";
      els.apiAlertIcon.textContent = meta.api_status === "quota_exhausted" ? "🪫" : "⚠️";
      els.apiAlertMessage.textContent = meta.status_message;
      return;
    }

    // 2. If neither internal server key nor user key exists -> Inform at top
    if (!hasServerKey && !userKey) {
      els.apiAlertBanner.style.display = "flex";
      els.apiAlertBanner.className = "api-alert-banner";
      els.apiAlertIcon.textContent = "🔑";
      els.apiAlertMessage.textContent =
        "No Gemini API key has been added on the server yet. Even Silk Board autos don't move for free—add your key to wake up the live AI!";
    } else {
      els.apiAlertBanner.style.display = "none";
    }
  }

  function updateTokenTelemetry(st, costUsd) {
    const totalTok = st.total_tokens || 0;
    const lastIn = st.last_turn_input_tokens || 0;
    const lastOut = st.last_turn_output_tokens || 0;
    const lastTot = st.last_turn_total_tokens || 0;
    const usd = typeof costUsd === "number" ? costUsd : 0;
    const inr = usd * 86;

    els.tokenShortText.textContent = `${totalTok} tok • $${usd.toFixed(4)}`;
    els.tpLastTurn.textContent = `${lastIn} in + ${lastOut} out (${lastTot})`;
    els.tpRunTotal.textContent = `${totalTok} tokens`;
    els.tpRunCost.textContent = `$${usd.toFixed(5)} (₹${inr.toFixed(3)})`;

    if (lastTot === 0 && totalTok === 0) {
      els.tpValidationBadge.textContent = "0 Tokens Used";
    } else if (lastTot <= 650) {
      els.tpValidationBadge.textContent = "✓ Lean (<650 tok/turn)";
      els.tpValidationBadge.style.color = "var(--emerald)";
    } else {
      els.tpValidationBadge.textContent = `${lastTot} tok/turn`;
      els.tpValidationBadge.style.color = "var(--amber)";
    }
  }

  els.tokenBadgeBtn.addEventListener("click", () => {
    const open = els.tokenPopover.style.display === "block";
    els.tokenPopover.style.display = open ? "none" : "block";
  });

  document.addEventListener("click", (e) => {
    if (
      els.tokenPopover.style.display === "block" &&
      !els.tokenPopover.contains(e.target) &&
      !els.tokenBadgeBtn.contains(e.target)
    ) {
      els.tokenPopover.style.display = "none";
    }
  });

  function openApiKeyModal() {
    els.apiKeyInput.value = getSavedApiKey();
    els.apiKeyModal.style.display = "flex";
    els.apiKeyInput.focus();
  }

  els.apiKeyBtn.addEventListener("click", openApiKeyModal);
  els.apiAlertActionBtn.addEventListener("click", openApiKeyModal);

  els.closeApiModalBtn.addEventListener("click", () => {
    els.apiKeyModal.style.display = "none";
  });

  els.saveApiKeyBtn.addEventListener("click", () => {
    const val = els.apiKeyInput.value.trim();
    if (val) {
      localStorage.setItem("esc_gemini_api_key", val);
    } else {
      localStorage.removeItem("esc_gemini_api_key");
    }
    updateApiKeyStatus();
    els.apiKeyModal.style.display = "none";
  });

  function initTheme() {
    const saved = localStorage.getItem("esc_theme") || "dark";
    document.documentElement.setAttribute("data-theme", saved);
    els.themeIcon.textContent = saved === "dark" ? "☀️" : "🌙";
  }

  els.themeToggleBtn.addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-theme") || "dark";
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("esc_theme", next);
    els.themeIcon.textContent = next === "dark" ? "☀️" : "🌙";
  });

  function showDelta(el, text, isPositiveGood = false) {
    if (!text) {
      el.textContent = "";
      return;
    }
    el.textContent = text;
    el.className = "hud-delta " + (isPositiveGood ? "pos" : "neg");
    setTimeout(() => {
      if (el.textContent === text) el.textContent = "";
    }, 3500);
  }

  function formatWeather(w) {
    if (w === "heavy_downpour") return "⛈️ Heavy Downpour";
    if (w === "light_drizzle") return "🌧️ Light Drizzle";
    return "🌫️ Humid Evening";
  }

  function renderRouteMap(deltas = null) {
    if (!currentState || !els.roadBase) return;

    const totalLen = els.roadBase.getTotalLength();
    const ratio = Math.min(1, Math.max(0, currentState.distance_km / totalAirportKm));

    els.roadFill.style.strokeDasharray = `${totalLen}`;
    els.roadFill.style.strokeDashoffset = `${totalLen * (1 - ratio)}`;

    const pt = els.roadBase.getPointAtLength(totalLen * ratio);
    els.playerVehicle.setAttribute("transform", `translate(${pt.x}, ${pt.y})`);

    els.landmarksLayer.innerHTML = "";
    landmarks.forEach((lm, idx) => {
      const lmRatio = Math.min(1, Math.max(0, lm.km / totalAirportKm));
      const lpt = els.roadBase.getPointAtLength(totalLen * lmRatio);
      const reached = currentState.distance_km >= lm.km;

      const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
      g.setAttribute("transform", `translate(${lpt.x}, ${lpt.y})`);

      const c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      c.setAttribute("r", idx === landmarks.length - 1 ? "9" : "6.5");
      c.setAttribute("fill", reached ? "#38bdf8" : "#1e293b");
      c.setAttribute("stroke", idx === landmarks.length - 1 ? "#10b981" : "#94a3b8");
      c.setAttribute("stroke-width", "2.2");

      const above = idx % 2 === 1;
      const labelY = above ? -16 : 22;

      const title = document.createElementNS("http://www.w3.org/2000/svg", "text");
      title.setAttribute("class", "lm-label");
      title.setAttribute("x", "0");
      title.setAttribute("y", String(labelY));
      title.setAttribute("text-anchor", idx === 0 ? "start" : idx === landmarks.length - 1 ? "end" : "middle");
      title.textContent = lm.name.split("/")[0].trim();

      const kmTxt = document.createElementNS("http://www.w3.org/2000/svg", "text");
      kmTxt.setAttribute("class", "lm-km");
      kmTxt.setAttribute("x", "0");
      kmTxt.setAttribute("y", String(labelY + 11));
      kmTxt.setAttribute("text-anchor", idx === 0 ? "start" : idx === landmarks.length - 1 ? "end" : "middle");
      kmTxt.textContent = `${lm.km} km`;

      g.appendChild(c);
      g.appendChild(title);
      g.appendChild(kmTxt);
      els.landmarksLayer.appendChild(g);
    });

    els.kmProgressPill.textContent = `${currentState.distance_km.toFixed(1)} / ${totalAirportKm.toFixed(0)} km`;
    els.currentLocBanner.textContent = `${currentState.location_label} (${currentState.distance_km.toFixed(1)} km)`;
    els.sceneContextText.textContent = currentState.active_scene_context || "";

    if (deltas) {
      if (deltas.km_delta > 0) {
        const meters = Math.round(deltas.km_delta * 1000);
        els.kmDeltaBadge.textContent =
          deltas.km_delta < 1 ? `+${meters}m moved` : `+${deltas.km_delta.toFixed(1)} km covered`;
        els.kmDeltaBadge.style.color = "var(--emerald)";
      } else {
        els.kmDeltaBadge.textContent = "0m moved (Talking / Negotiating)";
        els.kmDeltaBadge.style.color = "var(--amber)";
      }
    } else {
      els.kmDeltaBadge.textContent = "At Silk Board (0 km)";
      els.kmDeltaBadge.style.color = "var(--text-sub)";
    }
  }

  function updateHUD(data, deltas = null) {
    const st = data.state;
    currentState = st;
    stateSignature = data.signature;

    els.clockValue.textContent = data.formatted_time;
    const minsLeft = data.minutes_remaining;
    if (minsLeft >= 0) {
      const h = Math.floor(minsLeft / 60);
      const m = minsLeft % 60;
      els.minsLeftText.textContent = h > 0 ? `${h}h ${m}m to check-in close` : `${m}m to check-in close`;
    } else {
      els.minsLeftText.textContent = `Check-in closed (${Math.abs(minsLeft)}m ago)`;
    }
    els.hudClockCard.classList.toggle("danger-pulse", minsLeft <= 25);

    els.battValue.textContent = `${st.battery}%`;
    els.battFill.style.width = `${st.battery}%`;
    els.battFill.style.backgroundColor =
      st.battery <= 10 ? "var(--rose)" : st.battery <= 20 ? "var(--amber)" : "var(--emerald)";
    els.hudBattCard.classList.toggle("danger-pulse", st.battery === 0);

    if (data.upi_enabled) {
      els.upiPill.textContent = "UPI WORKS";
      els.upiPill.className = "upi-pill upi-ok";
    } else {
      els.upiPill.textContent = "DEAD • NO UPI";
      els.upiPill.className = "upi-pill upi-dead";
    }

    els.cashValue.textContent = `₹${st.cash}`;
    const items = st.inventory || [];
    els.bagCount.textContent = `${items.length} item${items.length === 1 ? "" : "s"}`;
    els.bagValue.textContent = items.length ? items.join(", ") : "Empty";
    els.modeSubText.textContent = st.transport_mode || "On foot";

    els.weatherBadge.textContent = formatWeather(st.weather);
    els.turnBadge.textContent = `Turn ${Math.min(st.turn, st.max_turns)} / ${st.max_turns}`;

    if (deltas) {
      if (deltas.time_delta) showDelta(els.clockDelta, `+${deltas.time_delta}m`, false);
      if (deltas.battery_delta) {
        const sign = deltas.battery_delta > 0 ? "+" : "";
        showDelta(els.battDelta, `${sign}${deltas.battery_delta}%`, deltas.battery_delta > 0);
      }
      if (deltas.cash_delta) {
        const sign = deltas.cash_delta > 0 ? "+" : "";
        showDelta(els.cashDelta, `${sign}₹${Math.abs(deltas.cash_delta)}`, deltas.cash_delta > 0);
      }
    }

    updateTokenTelemetry(st, data.estimated_cost_usd || 0);
    updateApiKeyStatus(data.meta || null);
    renderRouteMap(deltas);

    if (st.status === "won" || st.status === "lost") {
      showEndModal(st, data.formatted_time, data.estimated_cost_usd || 0);
    }
  }

  function appendPlayerMessage(actionText, timeStr, turnNum) {
    const row = document.createElement("div");
    row.className = "chat-row player-row";

    const meta = document.createElement("div");
    meta.className = "player-meta";
    meta.textContent = `YOU • TURN ${turnNum} (${timeStr})`;

    const bubble = document.createElement("div");
    bubble.className = "player-chat-bubble";
    bubble.textContent = actionText;

    row.appendChild(meta);
    row.appendChild(bubble);
    els.storyFeed.appendChild(row);
    els.storyFeed.scrollTop = els.storyFeed.scrollHeight;
  }

  function showTypingIndicator() {
    const row = document.createElement("div");
    row.className = "chat-row ai-row";
    row.id = "activeTypingRow";
    row.innerHTML = `
      <div class="typing-bubble">
        <div class="typing-dots"><span></span><span></span><span></span></div>
        <span>Bengaluru streets responding...</span>
      </div>
    `;
    els.storyFeed.appendChild(row);
    els.storyFeed.scrollTop = els.storyFeed.scrollHeight;
  }

  function removeTypingIndicator() {
    const el = document.getElementById("activeTypingRow");
    if (el) el.remove();
  }

  function appendAiResponse({ speakerName, spokenResponse, sceneExplanation, ruleNotice, timeStr, locLabel, deltas, turnTokens }) {
    const row = document.createElement("div");
    row.className = "chat-row ai-row";

    const card = document.createElement("article");
    card.className = "ai-chat-card";

    const head = document.createElement("div");
    head.className = "ai-card-header";
    head.innerHTML = `
      <span class="speaker-badge">🗣️ ${speakerName || "Auto Driver"}</span>
      <span class="turn-time-tag">${timeStr} • 📍 ${locLabel}</span>
    `;
    card.appendChild(head);

    if (spokenResponse) {
      const mainSpeech = document.createElement("div");
      mainSpeech.className = "driver-main-response";
      mainSpeech.textContent = spokenResponse;
      card.appendChild(mainSpeech);
    }

    if (sceneExplanation) {
      const smallNote = document.createElement("p");
      smallNote.className = "scene-small-explanation";
      smallNote.textContent = sceneExplanation;
      card.appendChild(smallNote);
    }

    if (ruleNotice) {
      const rBanner = document.createElement("div");
      rBanner.className = "rule-notice-banner";
      rBanner.innerHTML = `<span>⚡</span><span>${ruleNotice}</span>`;
      card.appendChild(rBanner);
    }

    if (deltas) {
      const dRow = document.createElement("div");
      dRow.className = "delta-pills";
      if (deltas.time_delta) {
        dRow.innerHTML += `<span class="d-pill">⏱️ +${deltas.time_delta}m</span>`;
      }
      if (deltas.battery_delta !== 0) {
        const s = deltas.battery_delta > 0 ? "+" : "";
        dRow.innerHTML += `<span class="d-pill">🔋 ${s}${deltas.battery_delta}%</span>`;
      }
      if (deltas.cash_delta !== 0) {
        dRow.innerHTML += `<span class="d-pill">💵 -₹${Math.abs(deltas.cash_delta)}</span>`;
      }
      if (deltas.km_delta > 0) {
        const distTxt =
          deltas.km_delta < 1 ? `+${Math.round(deltas.km_delta * 1000)}m` : `+${deltas.km_delta.toFixed(1)} km`;
        dRow.innerHTML += `<span class="d-pill" style="color:var(--emerald)">🛺 ${distTxt}</span>`;
      } else {
        dRow.innerHTML += `<span class="d-pill">💬 Stationary</span>`;
      }
      if (typeof turnTokens === "number" && turnTokens > 0) {
        dRow.innerHTML += `<span class="d-pill">⚡ ${turnTokens} tok</span>`;
      }
      card.appendChild(dRow);
    }

    row.appendChild(card);
    els.storyFeed.appendChild(row);
    els.storyFeed.scrollTop = els.storyFeed.scrollHeight;
  }

  function showEndModal(st, formattedTime, costUsd) {
    const won = st.status === "won";
    els.endBadge.textContent = won ? "AT THE COUNTER IN TIME" : "FLIGHT MISSED";
    els.endBadge.style.background = won ? "rgba(16, 185, 129, 0.2)" : "rgba(244, 63, 94, 0.2)";
    els.endBadge.style.color = won ? "var(--emerald)" : "var(--rose)";

    els.endTitle.textContent = won ? "Flight FL 2047 Boarded!" : "Stranded in Bengaluru Traffic";
    els.endReasonText.textContent = st.end_reason || "";
    els.finalClockStat.textContent = formattedTime;
    els.finalBattStat.textContent = `${st.battery}%`;
    els.finalCashStat.textContent = `₹${st.cash}`;
    els.finalCostStat.textContent = `$${(costUsd || 0).toFixed(4)}`;
    els.endModal.style.display = "flex";
  }

  async function startNewGame() {
    els.endModal.style.display = "none";
    els.storyFeed.innerHTML = "";

    try {
      const res = await fetch("/api/start", { method: "POST" });
      const data = await res.json();
      landmarks = data.landmarks || [];
      totalAirportKm = data.total_km || 38.0;
      hasServerKey = Boolean(data.has_server_key);
      updateHUD(data);

      appendAiResponse({
        speakerName: data.state.last_speaker_name || "Auto Driver (Ramesh)",
        spokenResponse: data.state.last_spoken_response,
        sceneExplanation: data.state.last_narrative,
        ruleNotice: null,
        timeStr: data.formatted_time,
        locLabel: data.state.location_label,
        deltas: null,
        turnTokens: 0,
      });
      els.commandInput.focus();
    } catch (err) {
      console.error("Failed to start game:", err);
    }
  }

  els.turnForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!currentState || currentState.status !== "playing") return;

    const action = els.commandInput.value.trim();
    if (!action) return;

    const turnBeingPlayed = currentState.turn;
    const clockBefore = els.clockValue.textContent;

    els.commandInput.value = "";
    appendPlayerMessage(action, clockBefore, turnBeingPlayed);
    showTypingIndicator();

    els.sendMoveBtn.disabled = true;
    els.sendBtnText.textContent = "...";

    try {
      const res = await fetch("/api/turn", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action,
          state: currentState,
          signature: stateSignature,
          api_key: getSavedApiKey() || null,
        }),
      });

      removeTypingIndicator();

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Turn failed");
      }

      const data = await res.json();
      if (data.meta && data.meta.model_used) {
        els.modelTag.textContent = data.meta.model_used;
      }

      updateHUD(data, data.deltas);

      appendAiResponse({
        speakerName: data.state.last_speaker_name,
        spokenResponse: data.state.last_spoken_response,
        sceneExplanation: data.state.last_narrative,
        ruleNotice: data.state.last_rule_notice,
        timeStr: data.formatted_time,
        locLabel: data.state.location_label,
        deltas: data.deltas,
        turnTokens: data.meta ? data.meta.total_tokens : 0,
      });
    } catch (err) {
      removeTypingIndicator();
      appendAiResponse({
        speakerName: "System",
        spokenResponse: `"Could not process move: ${err.message}"`,
        sceneExplanation: "Your game state was preserved without changes.",
        ruleNotice: null,
        timeStr: els.clockValue.textContent,
        locLabel: currentState.location_label,
        deltas: null,
        turnTokens: 0,
      });
    } finally {
      els.sendMoveBtn.disabled = false;
      els.sendBtnText.textContent = "Send →";
      els.commandInput.focus();
    }
  });

  els.newGameBtn.addEventListener("click", startNewGame);
  els.playAgainModalBtn.addEventListener("click", startNewGame);

  initTheme();
  startNewGame();
})();
