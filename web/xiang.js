"use strict";

const $ = id => document.getElementById(id);
const words = {
  "chess-title": ["中国象棋", "Chinese Chess"], deselect: ["取消选棋", "Deselect"],
  "lan-title": ["局域网联机", "LAN play"],
  guide: ["双方连接到同一局域网，使用 6 位房间码配对。", "Connect to the same LAN and pair with a 6-digit room code."],
  "host-red-label": ["房主执红", "Host plays red"], "undo-label": ["允许悔棋", "Allow undo"],
  "sound-label": ["音效", "Sound"], host: ["创建房间", "Create room"], "code-label": ["房间码", "Room code"],
  join: ["加入房间", "Join room"], undo: ["悔棋", "Undo"], rematch: ["重新开始", "Play again"],
  leave: ["离开房间", "Leave room"], creating: ["正在配对…", "Pairing…"],
  waiting: ["等待对手。房间码 5 分钟内有效。", "Waiting for opponent. Code valid for 5 minutes."],
  red: ["红方", "Red"], black: ["黑方", "Black"], your_turn: ["你执{}，请走棋", "Your turn ({})"],
  opponent_turn: ["等待{}走棋", "Waiting for {}"], win: ["{}胜", "{} wins"], draw: ["和棋", "Draw"],
  mate: ["将死", "Checkmate"], stalemate: ["困毙", "Stalemate"], check: ["将军", "Check"],
  perpetual: ["长将判负", "Perpetual check"], repetition: ["重复局面", "Repetition"],
  rematch_requested: ["对手请求再来一局", "Opponent wants a rematch"],
  rematch_wait: ["等待对手确认再来一局", "Waiting for rematch confirmation"],
  room_closed: ["房间已结束", "Room closed"], pair_expired: ["房间码已过期", "Room code expired"],
  wrong_code: ["房间码错误", "Wrong room code"], stale_move: ["棋局已更新", "Board updated"],
  illegal_move: ["不能走这一步", "Illegal move"], cannot_undo: ["当前无法悔棋", "Cannot undo now"],
  pair_unavailable: ["配对服务暂不可用", "Pairing service unavailable"],
  pair_failed: ["配对失败，请重试", "Pairing failed. Try again."],
};
const letters = ["", "帥", "仕", "相", "馬", "車", "炮", "兵"];
const blackLetters = ["", "將", "士", "象", "馬", "車", "炮", "卒"];
const sound = new Audio("stone.wav");
let language = localStorage.getItem("xiang-language") === "en" ? 1 : 0;
let game = new XiangGame(), peer = null, state = null, color = 0, code = "", selected = null;
let busy = false, notice = "", polling = false;
const tr = key => words[key][language];
const sideText = value => tr(value === RED ? "red" : "black");
const canMove = () => state?.ready && !busy && !peer.closed && !game.ended && game.turn === color;
const buttons = game.board.map((_, index) => {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "cell";
  button.addEventListener("click", () => choose(index));
  button.addEventListener("keydown", event => {
    const delta = {ArrowUp: [0, -1], ArrowDown: [0, 1], ArrowLeft: [-1, 0], ArrowRight: [1, 0]}[event.key];
    if (!delta) return;
    event.preventDefault();
    const [x, y] = xy(index), [dx, dy] = delta;
    const ranked = buttons.flatMap((cell, position) => {
      if (position === index || cell.disabled) return [];
      const [px, py] = xy(position);
      const forward = (px - x) * dx + (py - y) * dy;
      const across = Math.abs((px - x) * dy - (py - y) * dx);
      const distance = forward < 0 ? forward + (dx ? W : H) : forward;
      return [{cell, group: forward > 0 ? 0 : forward < 0 ? 1 : 2, score: across * 2 + distance}];
    });
    ranked.sort((a, b) => a.group - b.group || a.score - b.score);
    ranked[0]?.cell.focus();
  });
  $("squares").append(button);
  return button;
});

function drawGrid() {
  const ctx = $("grid").getContext("2d");
  ctx.strokeStyle = ctx.fillStyle = "#78542f";
  ctx.lineWidth = 1.5;
  const line = (x, y, dx, dy) => {
    ctx.moveTo(25 + 50 * x, 25 + 50 * y);
    ctx.lineTo(25 + 50 * dx, 25 + 50 * dy);
  };
  ctx.beginPath();
  for (let y = 0; y < H; y++) line(0, y, 8, y);
  for (let x = 0; x < W; x++) {
    if (x === 0 || x === 8) line(x, 0, x, 9);
    else { line(x, 0, x, 4); line(x, 5, x, 9); }
  }
  for (const y of [0, 7]) { line(3, y, 5, y + 2); line(5, y, 3, y + 2); }
  ctx.stroke();
  ctx.font = "28px KaiTi, serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText("楚河", 125, 250);
  ctx.fillText("漢界", 325, 250);
}

function translate() {
  document.documentElement.lang = language ? "en" : "zh-CN";
  document.title = tr("chess-title");
  $("language").textContent = language ? "简体中文" : "English";
  for (const [id, values] of Object.entries(words)) {
    if ($(id)) $(id).textContent = values[language];
  }
}

function render() {
  const targets = selected === null ? [] : [...game.destinations(selected)];
  const last = game.moves[game.moves.length - 1] || [];
  const checkedGeneral = game.check ? game.board.indexOf(game.turn === RED ? KING : -KING) : -1;
  const playable = canMove();
  buttons.forEach((button, cell) => {
    const index = color === BLACK ? W * H - 1 - cell : cell;
    const piece = game.board[index], [x, y] = xy(index);
    const letter = (piece < 0 ? blackLetters : letters)[Math.abs(piece)];
    button.classList.toggle("selected", selected === index);
    button.classList.toggle("last", last.includes(index));
    button.classList.toggle("target", targets.includes(index) && !piece);
    button.classList.toggle("capture", targets.includes(index) && Boolean(piece));
    button.classList.toggle("check", checkedGeneral === index);
    button.setAttribute("aria-label", `${String.fromCharCode(65 + x)}${y + 1} ${piece ? sideText(colorOf(piece)) + " " + letter : ""}`);
    const actionable = selected === null ? piece && colorOf(piece) === color
      && !game.destinations(index).next().done : targets.includes(index);
    button.disabled = !playable || !actionable;
    if (button.textContent !== letter || (button.firstChild?.classList.contains("red") || false) !== (piece > 0)) {
      button.textContent = "";
      if (piece) {
        const disc = document.createElement("span");
        disc.className = piece > 0 ? "disc red" : "disc";
        disc.textContent = letter;
        button.append(disc);
      }
    }
  });
  $("setup").hidden = Boolean(peer);
  $("actions").hidden = !peer;
  $("deselect").hidden = selected === null;
  $("undo").hidden = !state?.undo || game.ended;
  $("undo").disabled = !playable || game.moves.length < 2;
  $("rematch").hidden = !game.ended;
  $("rematch").disabled = busy || !peer || peer.closed || state?.rematch.includes(color);
  $("room-code").hidden = !code || Boolean(state?.ready) || Boolean(peer?.closed);
  $("room-code").textContent = code;
  let status = notice && tr(words[notice] ? notice : "pair_failed");
  if (!status && peer) {
    if (peer.closed) status = tr(words[peer.error] ? peer.error : "room_closed");
    else if (!state?.ready) status = tr(state ? "waiting" : "creating");
    else if (game.ended) {
      status = (game.winner ? tr("win").replace("{}", sideText(game.winner)) : tr("draw")) + " · " + tr(game.reason);
      if (state.rematch.length) status += " · " + tr(state.rematch.includes(color) ? "rematch_wait" : "rematch_requested");
    } else {
      status = tr(game.turn === color ? "your_turn" : "opponent_turn").replace("{}", sideText(game.turn));
      if (game.check) status += " · " + tr("check");
    }
  }
  $("status").textContent = status;
}

function applyState(next) {
  if (next.variant !== "xiang" || !Array.isArray(next.moves)) throw new Error("pair_failed");
  const moves = next.moves;
  if (!state || state.revision !== next.revision || state.round !== next.round) {
    const extendsGame = state?.round === next.round && game.moves.length <= moves.length &&
      game.moves.every(([source, dest], i) => source === moves[i][0] && dest === moves[i][1]);
    const updated = extendsGame ? game : new XiangGame();
    for (const [source, dest] of moves.slice(updated.moves.length)) {
      if (!updated.play(source, dest)) throw new Error("pair_failed");
    }
    const played = extendsGame && moves.length > (state?.moves.length ?? 0);
    if (played && $("sound").checked) {
      sound.currentTime = 0;
      sound.play().catch(() => {});
    }
    game = updated;
    selected = null;
  }
  state = next;
}

async function start(hosting) {
  if (peer || busy) return;
  let connection;
  try {
    notice = "";
    connection = new BrowserPeer(hosting ? new PeerMatch($("host-red").checked, $("allow-undo").checked) : null);
    peer = connection;
    busy = true;
    render();
    const response = hosting ? await connection.host() : await connection.join($("code").value);
    if (peer !== connection) return;
    color = response.color;
    code = response.code || "";
    applyState(response.state);
  } catch (error) {
    if (peer !== connection && connection) return;
    drop();
    notice = error.message;
  } finally {
    if (peer === connection || !peer) busy = false;
    render();
  }
}

function drop() {
  peer?.close();
  peer = state = selected = null;
  game = new XiangGame();
  color = 0;
  code = notice = "";
  busy = false;
}

async function request(action, body = {}) {
  if (!peer || busy || peer.closed) return;
  const connection = peer;
  busy = true;
  notice = "";
  render();
  try {
    const next = await connection.call(action, {...body, revision: state.revision});
    if (peer === connection) applyState(next);
  } catch (error) {
    if (peer === connection) notice = error.message;
  } finally {
    if (peer === connection) busy = false;
    render();
  }
}

function choose(cell) {
  if (!canMove()) return;
  const index = color === BLACK ? W * H - 1 - cell : cell;
  notice = "";
  if (selected === null && colorOf(game.board[index]) === color
      && !game.destinations(index).next().done) selected = index;
  else if (selected !== null) {
    if ([...game.destinations(selected)].includes(index)) {
      request("move", {source: selected, dest: index, ply: game.moves.length});
      return;
    }
    notice = "illegal_move";
  }
  render();
  if (selected !== null) buttons.find(button => !button.disabled)?.focus();
}

function deselect() {
  if (selected === null) return;
  const cell = color === BLACK ? W * H - 1 - selected : selected;
  selected = null;
  render();
  if (!buttons[cell].disabled) buttons[cell].focus();
}

$("deselect").addEventListener("click", deselect);
window.addEventListener("keydown", event => {
  if (selected !== null && ["Escape", "Backspace"].includes(event.key)) {
    event.preventDefault();
    deselect();
  }
});

$("language").addEventListener("click", () => {
  language = 1 - language;
  localStorage.setItem("xiang-language", language ? "en" : "zh");
  translate();
  render();
});
$("host").addEventListener("click", () => start(true));
$("join-form").addEventListener("submit", event => { event.preventDefault(); start(false); });
$("undo").addEventListener("click", () => request("undo"));
$("rematch").addEventListener("click", () => request("rematch"));
$("leave").addEventListener("click", () => { drop(); render(); });
window.addEventListener("pagehide", drop);
window.setInterval(async () => {
  if (!peer || busy || polling || !state) return;
  if (peer.closed) { render(); return; }
  const connection = peer, before = state;
  polling = true;
  try {
    const next = await connection.call("state", {});
    if (connection === peer && state === before && !busy) applyState(next);
  } catch (error) {
    if (connection === peer && !connection.closed) notice = error.message;
  } finally {
    polling = false;
    render();
  }
}, 400);

drawGrid();
translate();
render();

