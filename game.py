"""Chinese chess rules shared by local games, LAN hosts and the engine."""

from dataclasses import dataclass

WIDTH, HEIGHT = 9, 10
RED, BLACK = 1, 2
KING, ADVISOR, ELEPHANT, HORSE, ROOK, CANNON, SOLDIER = range(1, 8)
ORTHOGONAL = ((1, 0), (-1, 0), (0, 1), (0, -1))
DIAGONAL = ((1, 1), (1, -1), (-1, 1), (-1, -1))
HORSE_STEPS = ((2, 1), (2, -1), (-2, 1), (-2, -1),
               (1, 2), (-1, 2), (1, -2), (-1, -2))
PIECE_STEPS = {KING: ORTHOGONAL, ADVISOR: DIAGONAL,
               ELEPHANT: tuple((dx * 2, dy * 2) for dx, dy in DIAGONAL), HORSE: HORSE_STEPS}
BACK_RANK = (ROOK, HORSE, ELEPHANT, ADVISOR, KING, ADVISOR, ELEPHANT, HORSE, ROOK)
INITIAL = [0] * (WIDTH * HEIGHT)
INITIAL[:WIDTH] = [-piece for piece in BACK_RANK]
INITIAL[-WIDTH:] = BACK_RANK
for column in (1, 7):
    INITIAL[2 * WIDTH + column] = -CANNON
    INITIAL[7 * WIDTH + column] = CANNON
for column in (0, 2, 4, 6, 8):
    INITIAL[3 * WIDTH + column] = -SOLDIER
    INITIAL[6 * WIDTH + column] = SOLDIER
INITIAL = tuple(INITIAL)


def square(x, y):
    return y * WIDTH + x if 0 <= x < WIDTH and 0 <= y < HEIGHT else -1


def coords(index):
    return index % WIDTH, index // WIDTH


def side(piece):
    return RED if piece > 0 else BLACK if piece < 0 else 0


def sign(color):
    return 1 if color == RED else -1


def home(y, direction):
    return y >= 5 if direction > 0 else y <= 4


def palace(x, y, direction):
    return 3 <= x <= 5 and (7 <= y <= 9 if direction > 0 else 0 <= y <= 2)


def targets(board, source):
    """Yield geometrically reachable squares, including attacks on the enemy general."""
    piece = board[source]
    if not piece:
        return
    kind = abs(piece)
    direction = 1 if piece > 0 else -1
    x, y = coords(source)
    if kind in (ROOK, CANNON):
        for dx, dy in ORTHOGONAL:
            nx, ny = x + dx, y + dy
            screen = False
            while (dest := square(nx, ny)) >= 0:
                occupant = board[dest]
                if kind == ROOK:
                    if occupant * direction <= 0:
                        yield dest
                    if occupant:
                        break
                elif not screen:
                    if occupant:
                        screen = True
                    else:
                        yield dest
                elif occupant:
                    if occupant * direction < 0:
                        yield dest
                    break
                nx, ny = nx + dx, ny + dy
        return

    if kind == KING:
        for row in range(y - direction, -1 if direction > 0 else HEIGHT, -direction):
            dest = square(x, row)
            if board[dest]:
                if board[dest] == -direction * KING:
                    yield dest
                break
    if kind == SOLDIER:
        steps = ((0, -direction),)
        if not home(y, direction):
            steps += ((1, 0), (-1, 0))
    else:
        steps = PIECE_STEPS[kind]
    for dx, dy in steps:
        nx, ny = x + dx, y + dy
        dest = square(nx, ny)
        if dest < 0 or board[dest] * direction > 0:
            continue
        if kind in (KING, ADVISOR) and not palace(nx, ny, direction):
            continue
        if kind == ELEPHANT and (not home(ny, direction)
                                 or board[square(x + dx // 2, y + dy // 2)]):
            continue
        if kind == HORSE:
            leg = square(x + (dx // 2 if abs(dx) == 2 else 0),
                         y + (dy // 2 if abs(dy) == 2 else 0))
            if board[leg]:
                continue
        yield dest


def checked(board, color):
    direction = sign(color)
    try:
        king = board.index(KING * direction)
    except ValueError:
        return True
    x, y = coords(king)
    for dx, dy in ORTHOGONAL:
        nx, ny = x + dx, y + dy
        screen = False
        while (dest := square(nx, ny)) >= 0:
            piece = board[dest]
            if piece:
                if screen:
                    if piece == -direction * CANNON:
                        return True
                    break
                if piece == -direction * ROOK or (dx == 0 and piece == -direction * KING):
                    return True
                screen = True
            nx, ny = nx + dx, ny + dy
    for dx, dy in HORSE_STEPS:
        source = square(x + dx, y + dy)
        if source >= 0 and board[source] == -direction * HORSE:
            leg = square(x + dx - (dx // 2 if abs(dx) == 2 else 0),
                         y + dy - (dy // 2 if abs(dy) == 2 else 0))
            if not board[leg]:
                return True
    for dx, dy in ((0, -direction), (-1, 0), (1, 0)):
        source = square(x + dx, y + dy)
        if (source >= 0 and board[source] == -direction * SOLDIER
                and (dx == 0 or not home(y, -direction))):
            return True
    # An opposing elephant or advisor can never reach this side's palace.
    return False


def push(board, move):
    source, dest = move
    captured = board[dest]
    board[dest], board[source] = board[source], 0
    return captured


def pop(board, move, captured):
    source, dest = move
    board[source], board[dest] = board[dest], captured


def legal_moves(board, color, source=None, *, captures_only=False):
    direction = sign(color)
    for index in range(len(board)) if source is None else (source,):
        if board[index] * direction <= 0:
            continue
        for dest in targets(board, index):
            if abs(board[dest]) == KING or (captures_only and not board[dest]):
                continue
            move = index, dest
            captured = push(board, move)
            safe = not checked(board, color)
            pop(board, move, captured)
            if safe:
                yield move


@dataclass(frozen=True)
class Result:
    winner: int = 0
    reason: str = ""


class Game:
    def __init__(self):
        self.board = list(INITIAL)
        self.history = []
        self.captures = []
        self.checks = []
        self.positions = [(RED, INITIAL)]
        self.result = Result()

    @property
    def turn(self):
        return RED if len(self.history) % 2 == 0 else BLACK

    @property
    def ended(self):
        return bool(self.result.reason)

    @property
    def in_check(self):
        return self.checks[-1] if self.checks else False

    def destinations(self, source):
        if self.ended or not 0 <= source < len(self.board):
            return ()
        return tuple(dest for _, dest in legal_moves(self.board, self.turn, source))

    def play(self, move):
        if (self.ended or not isinstance(move, (tuple, list)) or len(move) != 2
                or any(type(index) is not int or not 0 <= index < len(self.board) for index in move)):
            return False
        source, dest = move
        if dest not in self.destinations(source):
            return False
        move = source, dest
        self.captures.append(push(self.board, move))
        self.history.append(move)
        self.checks.append(checked(self.board, self.turn))
        position = self.turn, tuple(self.board)
        self.positions.append(position)
        if next(legal_moves(self.board, self.turn), None) is None:
            self.result = Result(3 - self.turn, "mate" if self.in_check else "stalemate")
        elif self.positions.count(position) >= 3:
            earlier = [i for i, entry in enumerate(self.positions[:-1]) if entry == position][-2]
            red, black = (all(self.checks[earlier + (parity - earlier) % 2::2])
                          for parity in (0, 1))
            self.result = Result(BLACK if red else RED, "perpetual") if red != black else Result(0, "repetition")
        return True

    def undo(self, count=1):
        for _ in range(min(count, len(self.history))):
            pop(self.board, self.history.pop(), self.captures.pop())
            self.checks.pop()
            self.positions.pop()
        self.result = Result()

