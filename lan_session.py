"""Keep Zero's LAN traffic off the display and keyboard loop."""

from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from time import monotonic

from game import BLACK, RED, Game
from lan import RoomError


class LanSession:
    def __init__(self, transport, code=None):
        self.code = code
        self.transport = transport
        self.hosting = code is None
        self.token = None
        self.color = 0
        self.game = None
        self.ready = False
        self.allow_undo = False
        self.revision = 0
        self.round_number = 1
        self.rematch_choices = None
        self.error = ""
        self.disconnected = False
        self.closed = False
        self.next_poll = 0
        self.pending_action = None
        self.worker = ThreadPoolExecutor(max_workers=1)
        self.action = "create" if self.hosting else "join"
        self.job = self.worker.submit(self.transport, self.action, code=code)

    @property
    def can_act(self):
        return (self.ready and not self.closed and not self.disconnected
                and self.pending_action is None and (self.job is None or self.action == "state"))

    @property
    def can_play(self):
        return self.can_act and not self.game.ended and self.game.turn == self.color

    @property
    def can_rematch(self):
        return (self.can_act and self.game.ended and self.rematch_choices is not None
                and self.color not in self.rematch_choices)

    def rematch(self):
        if self.can_rematch:
            self.pending_action = ("rematch", self.revision, {})

    def move(self, move):
        if self.can_play:
            self.pending_action = ("move", self.revision, {"source": move[0], "dest": move[1],
                                                          "ply": len(self.game.history)})

    def undo(self):
        if self.can_play and self.allow_undo and len(self.game.history) >= 2:
            self.pending_action = ("undo", self.revision, {})

    def tick(self):
        changed = False
        if self.job is not None and self.job.done():
            job, action = self.job, self.action
            self.job = None
            was_disconnected = self.disconnected
            starting = action in ("create", "join")
            try:
                state = job.result()
                if starting:
                    token, color = state["token"], state["color"]
                    self.code = state.get("code", self.code)
                    state = state["state"]
                if state["variant"] != "xiang" or (starting and color not in (RED, BLACK)):
                    raise RoomError("pair_failed")
                history = [tuple(move) for move in state["moves"]]
                round_number = state.get("round", 1)
                rematch_choices = state.get("rematch")
                game = self.game
                if game is None or game.history != history or round_number != self.round_number:
                    game = Game()
                    # Reuse the reconstructed prefix for each new move.
                    if (self.game is not None and round_number == self.round_number
                            and history[:len(self.game.history)] == self.game.history):
                        game = deepcopy(self.game)
                    for move in history[len(game.history):]:
                        if not game.play(move):
                            raise ValueError("Invalid room history")
                if starting:
                    self.token, self.color = token, color
                changed = (self.game is None or self.game.history != game.history
                           or round_number != self.round_number or rematch_choices != self.rematch_choices
                           or self.ready != state["ready"] or was_disconnected)
                if action in ("move", "undo", "rematch") or changed:
                    self.error = ""
                self.game, self.ready = game, state["ready"]
                self.revision = state.get("revision", len(history))
                self.round_number, self.rematch_choices = round_number, rematch_choices
                self.allow_undo = state.get("undo", False)
                self.disconnected = False
                self.next_poll = monotonic() + .35
            except RoomError as error:
                self.error = error.code
                self.closed = starting or error.code in ("room_closed", "pair_expired", "pair_failed")
                self.next_poll = monotonic()
                changed = True
            except (OSError, ValueError, KeyError, TypeError, IndexError):
                self.disconnected = True
                if starting:
                    self.error = "connection_error"
                    self.closed = True
                self.next_poll = monotonic() + 1
                changed = not was_disconnected
        if self.token and not self.closed and self.job is None:
            if self.pending_action is not None:
                action, revision, body = self.pending_action
                self.pending_action = None
                allowed = self.can_rematch if action == "rematch" else self.can_play
                if allowed and revision == self.revision:
                    self.action = action
                    self.job = self.worker.submit(self.transport, action, token=self.token,
                                                  revision=revision, **body)
            if self.job is None and monotonic() >= self.next_poll:
                self.action = "state"
                self.job = self.worker.submit(self.transport, "state", token=self.token)
        return changed

    def close(self):
        self.closed = True
        token, starting = self.token, self.job if self.action in ("create", "join") else None

        def leave():
            try:
                seat = token or (starting.result()["token"] if starting else None)
                if seat:
                    self.transport("leave", token=seat)
            except (OSError, ValueError, RoomError, KeyError, TypeError):
                pass
            finally:
                self.transport.close()

        self.worker.submit(leave)
        self.worker.shutdown(wait=False)
