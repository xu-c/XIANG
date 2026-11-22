"""Authoritative Chinese chess state for a room hosted by Zero."""

import secrets

from game import RED, BLACK, Game


class RoomError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class Room:
    def __init__(self, host_first, undo):
        self.game = Game()
        self.host_color = RED if host_first else BLACK
        self.allow_undo = undo
        self.revision = 0
        self.round_number = 1
        self.rematch = set()
        self.players = {}
        self.closed = False

    def snapshot(self):
        return {
            "variant": "xiang", "moves": self.game.history.copy(), "ready": len(self.players) == 2,
            "turn": self.game.turn, "ended": self.game.ended, "winner": self.game.result.winner,
            "reason": self.game.result.reason, "check": self.game.in_check, "undo": self.allow_undo,
            "revision": self.revision, "round": self.round_number, "rematch": sorted(self.rematch),
        }

    def add_player(self):
        if len(self.players) >= 2:
            raise RoomError("room_full")
        color = self.host_color if not self.players else 3 - self.host_color
        token = secrets.token_hex(24)
        self.players[token] = color
        return {"token": token, "color": color, "state": self.snapshot()}

    def call(self, action, body, token):
        if self.closed or token not in self.players:
            raise RoomError("room_closed")
        color = self.players[token]
        if action == "join":
            return {"color": color, "state": self.snapshot()}
        if action == "leave":
            self.closed = True
            return {}
        if action == "state":
            return self.snapshot()
        if action not in ("move", "undo", "rematch"):
            raise RoomError("invalid_request")
        if len(self.players) != 2:
            raise RoomError("not_turn")
        if type(body.get("revision")) is not int or body["revision"] != self.revision:
            raise RoomError("stale_move")
        if action == "rematch":
            if not self.game.ended:
                raise RoomError("not_turn")
            self.rematch.add(color)
            if len(self.rematch) == 2:
                self.game = Game()
                self.rematch.clear()
                self.round_number += 1
                self.revision += 1
            return self.snapshot()
        if self.game.ended or self.game.turn != color:
            raise RoomError("not_turn")
        if action == "undo":
            if not self.allow_undo or len(self.game.history) < 2:
                raise RoomError("cannot_undo")
            self.game.undo(2)
        else:
            if type(body.get("ply")) is not int or body["ply"] != len(self.game.history):
                raise RoomError("stale_move")
            if not self.game.play((body.get("source"), body.get("dest"))):
                raise RoomError("illegal_move")
        self.revision += 1
        return self.snapshot()

