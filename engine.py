"""Offline iterative-deepening alpha-beta search for Cardputer Zero."""

from time import monotonic

from game import (ADVISOR, CANNON, ELEPHANT, HORSE, KING, ROOK, SOLDIER,
                  checked, coords, home, legal_moves, pop, push, sign)

LEVELS = {"easy": (2, .24), "normal": (4, .7), "hard": (6, 1.6)}
VALUES = (0, 10000, 115, 115, 285, 590, 305, 85)
MATE = 30000


class SearchTimeout(Exception):
    pass


def piece_value(piece, index):
    kind = abs(piece)
    x, y = coords(index)
    center = 4 - abs(4 - x)
    advance = 9 - y if piece > 0 else y
    if kind == SOLDIER:
        return VALUES[kind] + advance * 4 + (22 + center * 8 if advance >= 5 else 0)
    if kind in (HORSE, CANNON, ROOK):
        return VALUES[kind] + center * (5 if kind == HORSE else 3) + min(advance, 6) * 3
    return VALUES[kind]


def evaluate(board, direction):
    return direction * sum(piece_value(piece, index) * (1 if piece > 0 else -1)
                           for index, piece in enumerate(board) if piece)


def pick_move(game, level):
    board = game.board.copy()
    color = game.turn
    depth_limit, seconds = LEVELS[level]
    deadline = monotonic() + seconds
    previous = set(game.positions)
    path = set()
    nodes = 0

    def priority(move):
        source, dest = move
        piece, victim = board[source], board[dest]
        return (10 * VALUES[abs(victim)] - VALUES[abs(piece)] if victim else 0
                ) + piece_value(piece, dest) - piece_value(piece, source)

    def search(turn, depth, alpha, beta, ply, quiet_depth):
        nonlocal nodes
        nodes += 1
        if nodes % 32 == 0 and monotonic() >= deadline:
            raise SearchTimeout
        position = turn, tuple(board)
        if position in path:
            return 0
        if depth <= 0 and (quiet_depth <= 0 or not checked(board, turn)):
            if next(legal_moves(board, turn), None) is None:
                return -MATE + ply
            score = evaluate(board, sign(turn))
            if quiet_depth <= 0 or score >= beta:
                return score
            alpha = max(alpha, score)
            moves = legal_moves(board, turn, captures_only=True)
        else:
            moves = list(legal_moves(board, turn))
            if not moves:
                return -MATE + ply
        path.add(position)
        try:
            for move in sorted(moves, key=priority, reverse=True):
                captured = push(board, move)
                try:
                    score = -search(3 - turn, depth - 1, -beta, -alpha, ply + 1,
                                    quiet_depth - (depth <= 0))
                finally:
                    pop(board, move, captured)
                if score >= beta:
                    return score
                alpha = max(alpha, score)
            return alpha
        finally:
            path.remove(position)

    moves = sorted(legal_moves(board, color), key=priority, reverse=True)
    if not moves:
        return None
    best = moves[0]
    for depth in range(1, depth_limit + 1):
        alpha, candidate = -MATE, best
        order = [best] + [move for move in moves if move != best]
        try:
            for move in order:
                captured = push(board, move)
                try:
                    repeats = (3 - color, tuple(board)) in previous
                    penalty = 12 if repeats else 0
                    score = -search(3 - color, depth - 1, -MATE, -alpha - penalty, 1,
                                    1 if level == "easy" else 2) - penalty
                finally:
                    pop(board, move, captured)
                if score > alpha:
                    alpha, candidate = score, move
            best = candidate
            if alpha >= MATE - depth:
                break
        except SearchTimeout:
            break
    return best

