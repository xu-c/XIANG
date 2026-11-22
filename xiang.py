"""XIANG entry point, keyboard controls, and local persistence."""

import argparse
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
import json
from math import ceil
import os
from pathlib import Path
from shutil import which
import subprocess
from tempfile import NamedTemporaryFile
from time import monotonic

from cursor import focus
from game import BLACK, RED, Game, coords, legal_moves, side, square
from lan_session import LanSession
from engine import LEVELS, pick_move
from rtc_peer import ROOM_CODE_LENGTH, RtcPeer

LANGUAGES = ("zh", "en")
COLORS = (RED, BLACK)
START_CURSOR = (4, 6)
EXIT_HOLD_SECONDS = 3
ENGINE_RETRY_DELAYS = (0.5, 1, 2, 4)
DIRECTIONS = {"up": (0, -1), "f": (0, -1), "down": (0, 1), "x": (0, 1),
              "left": (-1, 0), "z": (-1, 0), "right": (1, 0), "c": (1, 0)}


@dataclass(frozen=True)
class Settings:
    level: str = "normal"
    language: str = "zh"
    sound: bool = True
    player_color: int = RED
    show_targets: bool = True


class App:
    def __init__(self, path):
        self.path = path
        self.settings = Settings()
        self.game = None
        self.mode = "cpu"
        self.level = "normal"
        self.player_color = RED
        self.cursor = START_CURSOR
        self.source = None
        self.lan_source = None
        self.lan_cursor = START_CURSOR
        self.page = "home"
        self.selected = 0
        self.pending = None
        self.lan = None
        self.room_host_first = True
        self.room_undo = False
        self.room_code = ""
        self.running = True
        self.escape_started = None
        self.exit_countdown = None
        self.dirty = True
        self.notice = ""
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.job = None
        self.reset_engine_retry()
        self.sound_path = Path(__file__).with_name("stone.wav")
        self.menu_sound_path = Path(__file__).with_name("menu.wav")
        self.aplay = which("aplay")
        self.sound_process = None
        self.load()

    def load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (ValueError, OSError):
            self.notice = "load_error"
            return
        try:
            settings = Settings(**data["settings"])
            if (settings.level not in LEVELS or settings.language not in LANGUAGES
                    or type(settings.sound) is not bool or type(settings.show_targets) is not bool
                    or type(settings.player_color) is not int or settings.player_color not in COLORS):
                raise ValueError("Invalid settings")
            self.settings = settings
            saved = data.get("game")
            if saved is None:
                return
            mode, level, player_color = (saved[key] for key in ("mode", "level", "player_color"))
            if (mode not in ("cpu", "local") or level not in LEVELS
                    or type(player_color) is not int or player_color not in COLORS):
                raise ValueError("Invalid game")
            game = Game()
            for move in saved["moves"]:
                if not game.play(move):
                    raise ValueError("Invalid move")
            if game.ended:
                raise ValueError("Completed game")
            self.game, self.mode, self.level = game, mode, level
            self.player_color = player_color
            self.cursor = coords(game.history[-1][1]) if game.history else START_CURSOR
            self.adjust_cursor(game)
        except (KeyError, ValueError, TypeError, AttributeError):
            self.notice = "load_error"

    def save(self):
        saved = None
        if self.game and not self.game.ended:
            saved = {"mode": self.mode, "level": self.level, "moves": self.game.history,
                     "player_color": self.player_color}
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                    delete=False) as stream:
                temporary = Path(stream.name)
                json.dump({"settings": vars(self.settings), "game": saved}, stream)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self.path)
        except OSError:
            self.notice = "save_error"
            if temporary:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

    def menu(self):
        if self.page == "settings":
            return [
                ("difficulty", self.settings.level),
                ("player_color", "play_red" if self.settings.player_color == RED else "play_black"),
                ("show_targets", "on" if self.settings.show_targets else "off"),
                ("language", self.settings.language),
                ("sound", "on" if self.settings.sound else "off"),
                ("rules_help", ""),
            ]
        if self.page == "confirm":
            return [("cancel", ""), ("replace", "")]
        if self.page == "lan":
            if self.lan is not None:
                return [("lan_resume", ""), ("lan_leave", ""), ("lan_help", "")]
            return [("lan_host", ""), ("lan_join", ""), ("lan_help", "")]
        if self.page == "lan_setup":
            return [("lan_first", "lan_host_side" if self.room_host_first else "lan_guest_side"),
                    ("undo", "on" if self.room_undo else "off"), ("lan_host", "")]
        rows = [("cpu", ""), ("local", ""), ("lan", ""), ("settings", "")]
        if self.game and not self.game.ended:
            rows.insert(0, ("resume", ""))
        return rows

    def open(self, page):
        self.page = page
        self.selected = 0
        self.reset_engine_retry()

    def reset_engine_retry(self):
        self.engine_failures = 0
        self.engine_retry_at = 0

    def start(self, mode):
        self.game = Game()
        self.mode, self.level = mode, self.settings.level
        self.player_color = self.settings.player_color
        self.begin_game()

    def begin_game(self):
        self.cursor = (4, 3) if self.flipped else START_CURSOR
        self.source = None
        self.adjust_cursor(self.game)
        self.open("game")
        self.save()

    def update_setting(self, row, direction):
        field, options = {
            "difficulty": ("level", LEVELS), "language": ("language", LANGUAGES),
            "player_color": ("player_color", COLORS),
            "sound": ("sound", (False, True)),
            "show_targets": ("show_targets", (False, True)),
        }[row]
        index = options.index(getattr(self.settings, field))
        value = options[(index + direction) % len(options)]
        self.settings = replace(self.settings, **{field: value})
        self.save()

    def handle(self, key, repeat=False):
        if not self.running:
            return
        if key == "escape":
            if not repeat and self.escape_started is None:
                self.escape_started = monotonic()
                self.exit_countdown = EXIT_HOLD_SECONDS
                self.dirty = True
            return
        if self.escape_started is not None:
            return
        direction = DIRECTIONS.get(key)
        if repeat and not direction:
            return
        self.dirty = True
        self.notice = ""
        if not repeat and self.page not in ("game", "lan_game"):
            typing_code = self.page == "lan_input" and (key == "backspace" or key in "0123456789")
            turning_off = (self.page == "settings" and self.menu()[self.selected][0] == "sound"
                           and self.settings.sound and (key == "enter" or direction and direction[0]))
            if (direction or key == "enter" or typing_code) and not turning_off:
                self.play_sound(menu=True)
        if self.page == "rules_help":
            if key == "enter":
                self.open("settings")
            return
        if self.page == "lan_help":
            if key == "enter":
                self.open("lan")
            return
        if self.page in ("lan_input", "lan_game"):
            self.handle_lan(key, direction)
            return
        if self.page == "game":
            if key == "enter" and self.game.ended:
                self.game = Game()
                self.begin_game()
            elif key == "u":
                self.undo()
            elif not self.game.ended and not self.computer_turn:
                self.handle_board(self.game, key, direction)
            return
        rows = self.menu()
        if direction and direction[1]:
            self.selected = (self.selected + direction[1]) % len(rows)
            return
        action = rows[self.selected][0]
        if self.page == "lan_setup":
            if key == "enter" or direction:
                if action == "lan_first":
                    self.room_host_first = not self.room_host_first
                elif action == "undo":
                    self.room_undo = not self.room_undo
                elif key == "enter":
                    self.start_lan()
            return
        if self.page == "settings":
            if action == "rules_help":
                if key == "enter":
                    self.open("rules_help")
            elif key == "enter" or direction:
                self.update_setting(action, direction[0] if direction else 1)
                if action == "sound" and self.settings.sound:
                    self.play_sound(menu=True)
            return
        if key != "enter":
            return
        if action in ("cpu", "local"):
            if self.game and not self.game.ended:
                self.pending = action
                self.open("confirm")
            else:
                self.start(action)
        elif action == "replace":
            self.start(self.pending)
        elif action == "lan_host":
            self.room_host_first, self.room_undo = True, False
            self.open("lan_setup")
        elif action == "lan_help":
            self.open("lan_help")
        elif action == "lan_join":
            self.room_code = ""
            self.open("lan_input")
        elif action == "lan_resume":
            self.open("lan_game")
        elif action == "lan_leave":
            self.leave_lan()
            self.open("lan")
        elif action == "lan":
            self.open("lan")
        elif action == "cancel":
            self.open("home")
        else:
            self.open("game" if action == "resume" else "settings")

    def start_lan(self):
        options = {"host_first": self.room_host_first, "undo": self.room_undo}
        self.lan = LanSession(RtcPeer(options))
        self.open("lan_game")

    def handle_lan(self, key, direction):
        if self.page == "lan_input":
            if key == "backspace":
                self.room_code = self.room_code[:-1]
            elif len(key) == 1 and key in "0123456789" and len(self.room_code) < ROOM_CODE_LENGTH:
                self.room_code += key
            elif key == "enter":
                if len(self.room_code) != ROOM_CODE_LENGTH:
                    self.notice = "lan_code_hint"
                    return
                self.lan = LanSession(RtcPeer(), self.room_code)
                self.open("lan_game")
            return
        session = self.lan
        if session.closed and key == "enter":
            self.leave_lan()
            self.open("lan")
        elif key == "enter" and session.game and session.game.ended:
            session.rematch()
        elif key == "u":
            self.clear_selection(session)
            session.undo()
        elif session.can_play:
            self.handle_board(session.game, key, direction, session)

    @property
    def flipped(self):
        return self.mode == "cpu" and self.player_color == BLACK

    def adjust_cursor(self, game, session=None, direction=None):
        if game.ended:
            return
        if session:
            source, cursor, flipped = self.lan_source, self.lan_cursor, session.color == BLACK
        else:
            source, cursor, flipped = self.source, self.cursor, self.flipped
        options = (game.destinations(source) if source is not None else
                   dict.fromkeys(start for start, _ in legal_moves(game.board, game.turn)))
        point = focus(cursor, options, direction, flipped)
        if session:
            self.lan_cursor = point
        else:
            self.cursor = point

    def clear_selection(self, session=None):
        source = self.lan_source if session else self.source
        if source is None:
            return False
        if session:
            self.lan_source, self.lan_cursor = None, coords(source)
        else:
            self.source, self.cursor = None, coords(source)
        return True

    def handle_board(self, game, key, direction, session=None):
        if direction:
            self.adjust_cursor(game, session, direction)
        elif key == "backspace":
            self.clear_selection(session)
        elif key == "enter":
            self.select_move(game, session)

    def select_move(self, game, session=None):
        source = self.lan_source if session else self.source
        target = square(*(self.lan_cursor if session else self.cursor))
        if source is None:
            if not game.destinations(target):
                return
            if session:
                self.lan_source = target
            else:
                self.source = target
            self.adjust_cursor(game, session)
        elif session:
            if target in game.destinations(source):
                self.lan_source = None
                session.move((source, target))
        elif game.play((source, target)):
            self.source = None
            self.adjust_cursor(game)
            self.play_sound()
            self.save()

    def leave_lan(self):
        if self.lan is not None:
            self.lan.close()
            self.lan = None
            self.lan_source = None

    def cancel_escape(self):
        if self.escape_started is not None:
            self.escape_started = None
            self.exit_countdown = None
            self.dirty = True

    def release_escape(self):
        if self.escape_started is None:
            return
        self.check_exit_hold()
        self.cancel_escape()
        if self.running and self.page != "home":
            self.play_sound(menu=True)
            if ((self.page == "game" and self.clear_selection())
                    or (self.page == "lan_game" and self.clear_selection(self.lan))):
                return
            if self.page in ("lan_game", "lan_input", "lan_setup", "lan_help"):
                if self.lan is not None and self.lan.closed:
                    self.leave_lan()
                self.open("lan")
            else:
                self.open("settings" if self.page == "rules_help" else "home")

    def check_exit_hold(self):
        if self.escape_started is None:
            return
        remaining = EXIT_HOLD_SECONDS - (monotonic() - self.escape_started)
        if remaining <= 0:
            self.running = False
        elif self.exit_countdown != ceil(remaining):
            self.exit_countdown = ceil(remaining)
            self.dirty = True

    @property
    def computer_turn(self):
        return self.mode == "cpu" and not self.game.ended and self.game.turn != self.player_color

    def undo(self):
        if not self.game.history:
            return
        count = 1
        if self.mode == "cpu" and side(self.game.board[self.game.history[-1][1]]) != self.player_color:
            count = 2
        if count > len(self.game.history):
            return
        self.cursor = coords(self.game.history[-count][0])
        self.source = None
        self.game.undo(count)
        self.adjust_cursor(self.game)
        self.reset_engine_retry()
        self.save()

    def tick(self):
        self.check_exit_hold()
        if not self.running:
            return
        if self.lan is not None:
            before = self.lan.game
            previous_round = self.lan.round_number
            if self.lan.tick():
                current = self.lan.game
                new_round = previous_round != self.lan.round_number
                if current is not None and (before is None or new_round):
                    self.lan_cursor = (4, 3) if self.lan.color == BLACK else START_CURSOR
                elif (before and current and len(before.history) > len(current.history)
                      and current.turn == self.lan.color):
                    self.lan_cursor = coords(before.history[len(current.history)][0])
                if current is not None and (before is None or before.history != current.history or new_round):
                    self.lan_source = None
                if current is not None and self.lan.can_play:
                    self.adjust_cursor(current, self.lan)
                if (self.page == "lan_game" and not new_round and before and current
                        and len(before.history) < len(current.history)):
                    self.play_sound()
                self.dirty = True
        if self.job and self.job[0].done():
            future, game, moves = self.job
            self.job = None
            if (self.page == "game" and game is self.game and moves == tuple(game.history)
                    and self.computer_turn):
                try:
                    move = future.result()
                except Exception:
                    move = None
                if move is not None and game.play(move):
                    self.adjust_cursor(game)
                    self.reset_engine_retry()
                    self.dirty = True
                    self.play_sound()
                    self.save()
                else:
                    delay = ENGINE_RETRY_DELAYS[self.engine_failures]
                    self.engine_retry_at = monotonic() + delay
                    self.engine_failures = min(self.engine_failures + 1, len(ENGINE_RETRY_DELAYS) - 1)
                    self.dirty = True
        if (self.page == "game" and self.computer_turn and self.job is None
                and monotonic() >= self.engine_retry_at):
            game = self.game
            snapshot = deepcopy(game)
            self.job = (self.executor.submit(pick_move, snapshot, self.level),
                        game, tuple(game.history))

    def play_sound(self, *, menu=False):
        if not self.settings.sound:
            return
        path = self.menu_sound_path if menu else self.sound_path
        try:
            if os.name == "nt":
                import winsound
                winsound.PlaySound(str(path), winsound.SND_FILENAME |
                                   winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            elif self.aplay:
                self.stop_sound()
                self.sound_process = subprocess.Popen(
                    [self.aplay, "-q", str(path)],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, RuntimeError):
            pass

    def stop_sound(self):
        if self.sound_process is not None and self.sound_process.poll() is None:
            self.sound_process.kill()
            self.sound_process.wait()

    def close(self):
        self.leave_lan()
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.stop_sound()


def preview(app, screen):
    import tkinter as tk
    from PIL import Image, ImageTk
    from ui import label as translate

    window = tk.Tk()
    window.title(translate("menu_title", app.settings.language))
    label = tk.Label(window, borderwidth=0, highlightthickness=0)
    label.pack()
    window.resizable(False, False)
    pressed = set()
    escape_release = None

    def key_down(event):
        nonlocal escape_release
        key = {"return": "enter"}.get(event.keysym.lower(), event.keysym.lower())
        if key == "escape" and escape_release is not None:
            window.after_cancel(escape_release)
            escape_release = None
        app.handle(key, key in pressed)
        pressed.add(key)

    def finish_escape_release():
        nonlocal escape_release
        escape_release = None
        pressed.discard("escape")
        app.release_escape()

    def key_up(event):
        nonlocal escape_release
        key = {"return": "enter"}.get(event.keysym.lower(), event.keysym.lower())
        if key == "escape":
            # X11 can send a release immediately before an autorepeat press.
            if escape_release is None:
                escape_release = window.after_idle(finish_escape_release)
        else:
            pressed.discard(key)

    def focus_out(event):
        nonlocal escape_release
        if escape_release is not None:
            window.after_cancel(escape_release)
            escape_release = None
        pressed.clear()
        app.cancel_escape()

    window.bind("<KeyPress>", key_down)
    window.bind("<KeyRelease>", key_up)
    window.bind("<FocusOut>", focus_out)

    def tick():
        app.tick()
        if not app.running:
            window.destroy()
            return
        if app.dirty:
            window.title(translate("menu_title", app.settings.language))
            image = screen.render(app).resize((640, 340), Image.Resampling.NEAREST)
            label.image = ImageTk.PhotoImage(image)
            label.configure(image=label.image)
            app.dirty = False
        window.after(24, tick)

    tick()
    window.mainloop()


def main():
    from ui import Screen

    parser = argparse.ArgumentParser(description="XIANG for Cardputer Zero")
    parser.add_argument("--device", action="store_true")
    parser.add_argument("--framebuffer", default="/dev/fb0")
    parser.add_argument("--keyboard")
    parser.add_argument("--rotate", action="store_true")
    parser.add_argument("--data", type=Path, default=Path(
        os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    ) / "xiang" / "state.json")
    args = parser.parse_args()
    screen = Screen()
    app = App(args.data)
    try:
        if args.device:
            from device import run
            run(app, screen, args.framebuffer, args.keyboard, args.rotate)
        else:
            preview(app, screen)
    finally:
        app.close()


if __name__ == "__main__":
    main()
