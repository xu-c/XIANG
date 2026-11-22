"use strict";

const W = 9, H = 10, RED = 1, BLACK = 2;
const KING = 1, ADVISOR = 2, ELEPHANT = 3, HORSE = 4, ROOK = 5, CANNON = 6, SOLDIER = 7;
const orthogonal = [[1, 0], [-1, 0], [0, 1], [0, -1]];
const diagonal = [[1, 1], [1, -1], [-1, 1], [-1, -1]];
const horses = [[2, 1], [2, -1], [-2, 1], [-2, -1], [1, 2], [1, -2], [-1, 2], [-1, -2]];
const back = [ROOK, HORSE, ELEPHANT, ADVISOR, KING, ADVISOR, ELEPHANT, HORSE, ROOK];
const initial = Array(W * H).fill(0);
initial.splice(0, W, ...back.map(piece => -piece));
initial.splice(9 * W, W, ...back);
for (const x of [1, 7]) {
  initial[2 * W + x] = -CANNON;
  initial[7 * W + x] = CANNON;
}
for (const x of [0, 2, 4, 6, 8]) {
  initial[3 * W + x] = -SOLDIER;
  initial[6 * W + x] = SOLDIER;
}

const sq = (x, y) => x >= 0 && x < W && y >= 0 && y < H ? y * W + x : -1;
const xy = index => [index % W, Math.floor(index / W)];
const colorOf = piece => piece > 0 ? RED : piece < 0 ? BLACK : 0;
const home = (y, d) => d > 0 ? y >= 5 : y <= 4;
const palace = (x, y, d) => 3 <= x && x <= 5 && (d > 0 ? y >= 7 && y <= 9 : y >= 0 && y <= 2);

function* targets(board, source) {
  const piece = board[source], kind = Math.abs(piece), d = Math.sign(piece);
  const [x, y] = xy(source);
  if (kind === ROOK || kind === CANNON) {
    for (const [dx, dy] of orthogonal) {
      let screen = false;
      for (let nx = x + dx, ny = y + dy; sq(nx, ny) >= 0; nx += dx, ny += dy) {
        const dest = sq(nx, ny), other = board[dest];
        if (kind === ROOK) {
          if (other * d <= 0) yield dest;
          if (other) break;
        } else if (!screen) {
          if (other) screen = true;
          else yield dest;
        } else if (other) {
          if (other * d < 0) yield dest;
          break;
        }
      }
    }
    return;
  }
  if (kind === KING) {
    for (let row = y - d; sq(x, row) >= 0; row -= d) {
      const dest = sq(x, row);
      if (!board[dest]) continue;
      if (board[dest] === -d * KING) yield dest;
      break;
    }
  }
  const steps = {
    [KING]: orthogonal, [ADVISOR]: diagonal,
    [ELEPHANT]: diagonal.map(([dx, dy]) => [2 * dx, 2 * dy]), [HORSE]: horses,
    [SOLDIER]: home(y, d) ? [[0, -d]] : [[0, -d], [1, 0], [-1, 0]],
  }[kind] || [];
  for (const [dx, dy] of steps) {
    const nx = x + dx, ny = y + dy, dest = sq(nx, ny);
    if (dest < 0 || board[dest] * d > 0) continue;
    if ((kind === KING || kind === ADVISOR) && !palace(nx, ny, d)) continue;
    if (kind === ELEPHANT && (!home(ny, d) || board[sq(x + dx / 2, y + dy / 2)])) continue;
    if (kind === HORSE && board[sq(x + Math.trunc(dx / 2), y + Math.trunc(dy / 2))]) continue;
    yield dest;
  }
}

function isChecked(board, turn) {
  const general = board.indexOf(turn === RED ? KING : -KING);
  if (general < 0) return true;
  return board.some((piece, source) => piece && colorOf(piece) !== turn &&
    Array.from(targets(board, source)).includes(general));
}

class XiangGame {
  constructor() {
    this.board = initial.slice();
    this.moves = [];
    this.captures = [];
    this.checks = [];
    this.positions = [this.position()];
    this.winner = 0;
    this.reason = "";
  }

  get turn() { return this.moves.length % 2 === 0 ? RED : BLACK; }
  get ended() { return Boolean(this.reason); }
  get check() { return this.checks[this.checks.length - 1] || false; }
  position() { return [this.turn, ...this.board].join(","); }

  *destinations(source) {
    if (this.ended || !Number.isInteger(source) || colorOf(this.board[source]) !== this.turn) return;
    for (const dest of targets(this.board, source)) {
      const captured = this.board[dest];
      if (Math.abs(captured) === KING) continue;
      this.board[dest] = this.board[source];
      this.board[source] = 0;
      const safe = !isChecked(this.board, this.turn);
      this.board[source] = this.board[dest];
      this.board[dest] = captured;
      if (safe) yield dest;
    }
  }

  play(source, dest) {
    if (!Array.from(this.destinations(source)).includes(dest)) return false;
    this.captures.push(this.board[dest]);
    this.board[dest] = this.board[source];
    this.board[source] = 0;
    this.moves.push([source, dest]);
    this.checks.push(isChecked(this.board, this.turn));
    const position = this.position();
    const previous = this.positions.flatMap((item, index) => item === position ? [index] : []);
    this.positions.push(position);
    if (!this.board.some((_, index) => !this.destinations(index).next().done)) {
      this.winner = 3 - this.turn;
      this.reason = this.check ? "mate" : "stalemate";
    } else if (previous.length >= 2) {
      const start = previous[previous.length - 2];
      const everyCheck = parity => this.checks.every((check, index) => index < start || index % 2 !== parity || check);
      const red = everyCheck(0), black = everyCheck(1);
      this.winner = red !== black ? (red ? BLACK : RED) : 0;
      this.reason = this.winner ? "perpetual" : "repetition";
    }
    return true;
  }

  undo(count) {
    for (let i = 0; i < count && this.moves.length; i++) {
      const [source, dest] = this.moves.pop();
      this.board[source] = this.board[dest];
      this.board[dest] = this.captures.pop();
      this.positions.pop();
      this.checks.pop();
    }
    this.winner = 0;
    this.reason = "";
  }
}

class PeerMatch {
  constructor(hostFirst, undo) {
    this.game = new XiangGame();
    this.hostColor = hostFirst ? RED : BLACK;
    this.undo = undo;
    this.revision = 0;
    this.round = 1;
    this.rematch = new Set();
    this.ready = false;
    this.closed = false;
  }

  state() {
    const game = this.game;
    return {variant: "xiang", moves: game.moves.slice(), ready: this.ready, turn: game.turn,
      ended: game.ended, winner: game.winner, reason: game.reason, check: game.check, undo: this.undo,
      revision: this.revision, round: this.round, rematch: [...this.rematch].sort()};
  }

  call(action, data, color) {
    const game = this.game;
    if (this.closed) throw new Error("room_closed");
    if (action === "join") return {color, state: this.state()};
    if (action === "leave") {
      this.closed = true;
      return {};
    }
    if (action === "state") return this.state();
    if (!["move", "undo", "rematch"].includes(action)) throw new Error("invalid_request");
    if (!this.ready) throw new Error("not_turn");
    if (data.revision !== this.revision) throw new Error("stale_move");
    if (action === "rematch") {
      if (!game.ended) throw new Error("not_turn");
      this.rematch.add(color);
      if (this.rematch.size === 2) {
        this.game = new XiangGame();
        this.rematch.clear();
        this.round++;
        this.revision++;
      }
      return this.state();
    }
    if (game.ended || game.turn !== color) throw new Error("not_turn");
    if (action === "undo") {
      if (!this.undo || game.moves.length < 2) throw new Error("cannot_undo");
      game.undo(2);
    } else {
      if (data.ply !== game.moves.length) throw new Error("stale_move");
      if (!game.play(data.source, data.dest)) throw new Error("illegal_move");
    }
    this.revision++;
    return this.state();
  }
}

