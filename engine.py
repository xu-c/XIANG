"""Run the upstream XQWLight engine outside XIANG's display loop."""

import json
from pathlib import Path
import subprocess

from game import legal_moves

LEVELS = ("easy", "normal", "hard")
ENTRY = Path(__file__).with_name("xqwlight") / "run.cjs"


def pick_move(game, level):
    try:
        answer = subprocess.run(
            ["node", str(ENTRY), str(LEVELS.index(level))],
            input=json.dumps(game.history), encoding="utf-8",
            capture_output=True, timeout=6, check=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        move = tuple(json.loads(answer.stdout))
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return move if move in legal_moves(game.board, game.turn) else None

