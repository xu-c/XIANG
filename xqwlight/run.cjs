// SPDX-License-Identifier: GPL-3.0-or-later
// Independent command-line adapter for the upstream XQWLight JavaScript engine.
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const levels = [10, 100, 1000]; // The upstream index.htm's three board.millis values.
const filenames = ["book.js", "position.js", "search.js"];
const source = filenames.map(name => fs.readFileSync(path.join(__dirname, name), "utf8")).join("\n");
const context = vm.createContext({
  history: JSON.parse(fs.readFileSync(0, "utf8")),
  millis: levels[Number(process.argv[2])],
});
if (!Number.isFinite(context.millis)) process.exit(2);

const move = vm.runInContext(source + `
  var position = new Position();
  position.fromFen("rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w");
  var toSquare = index => COORD_XY(index % 9 + 3, Math.floor(index / 9) + 3);
  var toIndex = square => (RANK_Y(square) - 3) * 9 + FILE_X(square) - 3;
  for (var [start, end] of history) {
    var step = MOVE(toSquare(start), toSquare(end));
    if (!position.legalMove(step) || !position.makeMove(step)) throw Error("Invalid move history");
  }
  var result = new Search(position, 16).searchMain(LIMIT_DEPTH, millis);
  result ? [toIndex(SRC(result)), toIndex(DST(result))] : null;
`, context, {timeout: 4700});
if (move) process.stdout.write(JSON.stringify(move));

