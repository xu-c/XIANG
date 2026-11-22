"""Shared 320 × 170 renderer."""

from functools import lru_cache
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from game import BLACK, RED, WIDTH, HEIGHT, INITIAL, coords, square, KING, sign

SIZE = (320, 170)
TITLE = "XIANG"
SHORT_CODE = "ZGXQ"
BG, PANEL, TEXT = "#141c20", "#243136", "#faf4e9"
MUTED, ACCENT = "#b6c4c2", "#a7e7ca"
WOOD, GRID = "#d8af75", "#78542f"
RED_INK, BLACK_INK = "#9b241e", "#24211e"
PIECES = ("", "帥", "仕", "相", "馬", "車", "炮", "兵")
DARK_PIECES = ("", "將", "士", "象", "馬", "車", "炮", "卒")

LABELS = {
    "menu_title": ("中国象棋", "Chinese Chess"),
    "unselect": ("取消选棋", "Deselect"),
    "select": ("选棋", "Select"),
    "lan": ("局域网联机", "LAN play"),
    "lan_host": ("创建房间", "Host room"),
    "lan_first": ("执红方", "Red side"),
    "lan_host_side": ("房主", "Host"),
    "lan_guest_side": ("加入方", "Guest"),
    "lan_help": ("联机说明", "LAN guide"),
    "cannot_undo": ("当前无法悔棋", "Cannot undo now"),
    "lan_join": ("加入房间", "Join room"),
    "lan_code_hint": ("请输入对手分享的 10 位房间码", "Enter the 10-digit code from your opponent"),
    "pair_failed": ("配对失败，请重新加入", "Pairing failed. Try joining again."),
    "pair_unavailable": ("配对服务暂不可用", "Pairing service unavailable"),
    "pair_expired": ("房间码已过期，请重新创建", "Code expired. Create a new room."),
    "rtc_missing": ("请安装 python3-aiortc", "Install python3-aiortc"),
    "lan_resume": ("返回对局", "Return to match"),
    "lan_leave": ("离开并结束房间", "Leave and close room"),
    "lan_code": ("房间码", "Room code"),
    "lan_wait": ("等待对手加入", "Waiting for opponent"),
    "lan_connecting": ("正在加入房间…", "Joining room…"),
    "lan_creating": ("正在创建房间…", "Creating room…"),
    "lan_code_validity": ("配对码 5 分钟内有效", "Code valid for 5 minutes"),
    "lan_reconnect": ("连接中断，正在重连", "Reconnecting…"),
    "wrong_code": ("房间码错误", "Wrong room code"),
    "room_full": ("房间已满", "Room is full"),
    "try_later": ("房间码尝试过多，请稍后重试", "Too many attempts. Try again shortly."),
    "room_closed": ("房间已结束", "Room closed"),
    "connection_error": ("连接失败", "Connection failed"),
    "not_turn": ("还不能走棋", "Cannot play now"),
    "stale_move": ("棋局已更新", "Board updated"),
    "lan_back": ("Enter / Esc  返回", "Enter / Esc  Back"),
    "cpu": ("离线人机", "Play computer"), "local": ("同机双人", "Two players"),
    "resume": ("继续对局", "Resume game"), "settings": ("设置", "Settings"),
    "difficulty": ("人机难度", "Difficulty"),
    "easy": ("入门", "Beginner"), "normal": ("业余", "Amateur"), "hard": ("专业", "Professional"),
    "language": ("语言", "Language"), "zh": ("简体中文", "简体中文"), "en": ("English", "English"),
    "on": ("开", "On"), "off": ("关", "Off"),
    "sound": ("音效", "Sound effects"),
    "rules_help": ("规则说明", "Rules guide"),
    "player_color": ("人机执棋", "Play as"),
    "play_black": ("执黑", "Black"), "play_red": ("执红", "Red"),
    "black_turn": ("黑方走棋", "Black to move"), "red_turn": ("红方走棋", "Red to move"),
    "your_black": ("你执黑，请走棋", "Your turn (Black)"),
    "your_red": ("你执红，请走棋", "Your turn (Red)"),
    "black_win": ("黑方胜", "Black wins"), "red_win": ("红方胜", "Red wins"),
    "cpu_black": ("电脑执黑，思考中", "Black CPU thinking"),
    "cpu_red": ("电脑执红，思考中", "Red CPU thinking"), "draw": ("和棋", "Draw"),
    "move_number": ("第 {} 手", "Move {}"),
    "mate": ("将死", "Checkmate"), "stalemate": ("困毙", "Stalemate"),
    "perpetual": ("长将判负", "Perpetual check"), "repetition": ("重复局面", "Repetition"),
    "check": ("将军", "Check"), "show_targets": ("显示可走棋位", "Show legal moves"),
    "select_piece": ("请先选择己方棋子", "Select your piece"),
    "illegal_move": ("不能走这一步", "Illegal move"),
    "selected": ("已选 {}", "Selected {}"),
    "save_error": ("无法保存", "Could not save"), "load_error": ("无法读取存档", "Could not load save"),
    "replace_title": ("替换上次对局？", "Replace saved game?"),
    "cancel": ("取消", "Cancel"), "replace": ("开始新局", "Start new game"),
    "choose": ("选择", "Select"), "change": ("修改", "Change"), "back": ("返回", "Back"),
    "place": ("走棋", "Move"), "undo": ("悔棋", "Undo"), "menu": ("菜单", "Menu"),
    "restart": ("重新开始", "Play again"),
    "rematch_wait": ("等待对手确认", "Waiting for opponent"),
    "rematch_accept": ("对手请求再来一局", "Opponent wants a rematch"),
    "hold_exit": ("长按 Esc 3 秒退出", "Hold Esc 3s to quit"),
    "exit_countdown": ("继续按住 Esc · {} 秒后退出", "Keep holding Esc · {}s to quit"),
}


def label(key, language):
    return LABELS[key][language == "en"]


def piece_text(piece):
    return (PIECES if piece > 0 else DARK_PIECES)[abs(piece)]


def piece_disc(draw, x, y, radius, letter, color, font, selected=False):
    draw.ellipse((x - radius, y - radius + 1, x + radius, y + radius + 1), fill="#81552e")
    draw.ellipse((x - radius, y - radius, x + radius, y + radius),
                 fill="#caf5b6" if selected else "#ffe6b6",
                 outline="#21644b" if selected else "#a97947")
    inset = max(1, radius // 11)
    r = radius - inset
    if radius >= 8:
        draw.ellipse((x - r, y - r, x + r, y + r), outline=color, width=max(1, radius // 40))
    left, top, right, bottom = draw.textbbox((0, 0), letter, font=font)
    draw.text((x - (left + right) / 2, y - (top + bottom) / 2), letter, font=font, fill=color)


def board(draw, rect, pieces, font, *, cursor=None, source=None, destinations=(),
          last=None, king_in_check=None, flipped=False):
    left, top, right, bottom = rect
    draw.rounded_rectangle(rect, radius=6, fill=WOOD)
    step = min((right - left - 16) // (WIDTH - 1), (bottom - top - 16) // (HEIGHT - 1))
    x0 = (left + right - step * (WIDTH - 1)) // 2
    y0 = (top + bottom - step * (HEIGHT - 1)) // 2
    x1, y1 = x0 + step * (WIDTH - 1), y0 + step * (HEIGHT - 1)

    def pixel(index):
        x, y = coords(index)
        if flipped:
            x, y = WIDTH - 1 - x, HEIGHT - 1 - y
        return x0 + x * step, y0 + y * step

    for row in range(HEIGHT):
        y = y0 + row * step
        draw.line((x0, y, x1, y), fill=GRID)
    for column in range(WIDTH):
        x = x0 + column * step
        if column in (0, WIDTH - 1):
            draw.line((x, y0, x, y1), fill=GRID)
        else:
            draw.line((x, y0, x, y0 + 4 * step), fill=GRID)
            draw.line((x, y0 + 5 * step, x, y1), fill=GRID)
    for y in (0, 7):
        for x, other in ((3, 5), (5, 3)):
            draw.line((*pixel(square(x, y)), *pixel(square(other, y + 2))), fill=GRID)
    river_y = (y0 + y1) // 2
    for x, label in ((2, "楚河"), (6, "漢界")):
        draw.text((x0 + x * step, river_y), label, font=font(max(8, step - 5)),
                  fill=GRID, anchor="mm")
    for index, piece in enumerate(pieces):
        if piece:
            x, y = pixel(index)
            piece_disc(draw, x, y, (step - 2) // 2, piece_text(piece),
                       RED_INK if piece > 0 else BLACK_INK, font(max(8, step - 4)), index == source)
    for index in destinations:
        x, y = pixel(index)
        if pieces[index]:
            r = step // 2
            draw.ellipse((x - r, y - r, x + r, y + r), outline="#256c52")
        else:
            draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill="#256c52")
    for index, tint in ((last[0] if last else None, "#778449"), (last[1] if last else None, "#778449"),
                        (king_in_check, "#b02423"), (source, "#247e5b"), (cursor, "#143f36")):
        if index is None:
            continue
        x, y = pixel(index)
        r = step // 2 + 1
        for dx in (-1, 1):
            for dy in (-1, 1):
                draw.line((x + dx * (r - 3), y + dy * r, x + dx * r, y + dy * r,
                           x + dx * r, y + dy * (r - 3)), fill=tint, width=2)


def icon():
    image = Image.new("RGBA", (256, 256))
    draw = ImageDraw.Draw(image)
    draw.ellipse((14, 22, 242, 250), fill="#583719")
    screen = Screen()
    font_path = Path("C:/Windows/Fonts/simkai.ttf")
    font = ImageFont.truetype(str(font_path), 144) if font_path.is_file() else screen.font(144)
    piece_disc(draw, 128, 121, 114, "象", BLACK_INK, font)
    return image.resize((128, 128), Image.Resampling.LANCZOS)


class Screen:
    def __init__(self):
        fonts = (os.environ.get("XIANG_FONT"), "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                 "/usr/share/APPLaunch/share/font/NotoSansCJK-Regular.ttc",
                 "C:/Windows/Fonts/msyh.ttc", "/System/Library/Fonts/PingFang.ttc")
        self.font_path = next((path for path in fonts if path and Path(path).is_file()), None)
        if not self.font_path:
            raise OSError("XIANG needs a CJK font. Install fonts-noto-cjk or set XIANG_FONT.")

    @lru_cache(maxsize=24)
    def font(self, size):
        return ImageFont.truetype(self.font_path, size, index=2 if "NotoSansCJK-Regular.ttc" in self.font_path else 0)

    def render(self, app):
        image = Image.new("RGB", SIZE, BG)
        draw = ImageDraw.Draw(image)
        lang = app.settings.language

        def tr(key):
            return label(key, lang)

        def text(x, y, value, size=12, color=TEXT, anchor="lt"):
            draw.text((x, y), value, fill=color, font=self.font(size), anchor=anchor)

        countdown = app.exit_countdown
        if countdown is not None:
            exit_message = tr("exit_countdown").format(countdown)

        if app.page == "lan_input":
            text(14, 9, tr("lan_join"), 18)
            text(14, 44, tr("lan_code_hint"), 12, ACCENT if app.notice else MUTED)
            draw.rounded_rectangle((14, 68, 303, 101), 4, fill=PANEL)
            text(22, 76, app.room_code + "_", 16, ACCENT)
            text(14, 151, exit_message if countdown is not None else "Enter  " + tr("lan_join"), 11, MUTED)
            return image

        session = app.lan if app.page == "lan_game" else None
        if session is not None and (session.closed or session.game is None or not session.ready):
            status = session.error or ("lan_reconnect" if session.disconnected else "lan_wait" if session.game else
                                       "lan_creating" if session.hosting else "lan_connecting")
            text(14, 9, tr("lan"), 18)
            text(14, 40, tr(status if status in LABELS else "connection_error"), 15, ACCENT)
            if session.hosting and session.code and not session.closed:
                text(14, 73, f"{tr('lan_code')}  {session.code}", 20, ACCENT)
                text(14, 106, tr("lan_code_validity"), 11, MUTED)
            text(14, 151, exit_message if countdown is not None else
                 tr("lan_back") if session.closed else "Esc  " + tr("menu"), 11, MUTED)
            return image

        if app.page == "game" or session is not None:
            game = session.game if session else app.game
            cursor = app.lan_cursor if session else app.cursor
            last = game.history[-1] if game.history else None
            source = app.lan_source if session else app.source
            flipped = session.color == BLACK if session else app.flipped
            board(draw, (1, 1, 168, 168), game.board, self.font,
                  cursor=(square(*cursor) if not game.ended and
                          (session.can_play if session else not app.computer_turn) else None),
                  source=source, last=last,
                  destinations=game.destinations(source) if source is not None and app.settings.show_targets else (),
                  king_in_check=game.board.index(sign(game.turn) * KING) if game.in_check else None,
                  flipped=flipped)
            text(177, 10, tr("menu_title"), 18)
            subtitle = (tr("lan") + "  ·  " + tr("play_black" if session.color == BLACK else "play_red")
                        if session else tr(app.mode) + "  ·  " +
                        (tr(app.level) if app.mode == "cpu" else "9 × 10"))
            text(177, 37, subtitle, 11, MUTED)
            color = game.result.winner if game.ended else game.turn
            if game.ended:
                status = {0: "draw", RED: "red_win", BLACK: "black_win"}[game.result.winner]
            elif session and session.disconnected:
                status = "lan_reconnect"
            elif session and color == session.color:
                status = "your_black" if color == BLACK else "your_red"
            elif session:
                status = "black_turn" if color == BLACK else "red_turn"
            elif app.computer_turn:
                status = "cpu_black" if color == BLACK else "cpu_red"
            elif app.mode == "cpu":
                status = "your_black" if color == BLACK else "your_red"
            else:
                status = "black_turn" if game.turn == BLACK else "red_turn"
            draw.rounded_rectangle((174, 54, 315, 84), radius=6, fill=PANEL, outline="#496561")
            if color:
                draw.ellipse((181, 63, 193, 75), fill=BLACK_INK if color == BLACK else "#d64d3f",
                             outline="#d6e7df")
            status_size = 12 if lang == "en" and (session or app.mode == "cpu") and not game.ended else 14
            text(200 if color else 182, 69, tr(status), status_size, ACCENT, "lm")
            if game.ended:
                details = tr(game.result.reason)
            elif session and session.error:
                details = tr(session.error if session.error in LABELS else "connection_error")
            elif app.notice:
                details = tr(app.notice)
            elif game.in_check:
                details = tr("check")
            elif source is not None:
                details = tr("selected").format(piece_text(game.board[source]))
            else:
                x, y = cursor
                details = tr("move_number").format(len(game.history) + (not game.ended))
                if not game.ended:
                    details += f"   {chr(65 + x)}{y + 1}"
            if game.ended:
                text(177, 88, details, 11, MUTED)
                if session and session.disconnected:
                    text(177, 113, tr("lan_reconnect"), 11, MUTED)
                elif not session or session.rematch_choices is not None:
                    votes = session.rematch_choices if session else ()
                    if session and session.color in votes:
                        text(177, 129, tr("rematch_wait"), 11, ACCENT)
                    else:
                        if votes:
                            text(177, 108, tr("rematch_accept"), 10, MUTED)
                        text(177, 129, "Enter  " + tr("restart"), 11, ACCENT)
            elif not session and app.engine_failures:
                error, retry = (("引擎故障", "正在自动重试") if lang == "zh"
                                else ("Engine error", "Retrying automatically"))
                text(177, 88, error, 11, MUTED)
                text(177, 106, retry, 11, TEXT)
            else:
                text(177, 88, details, 11, MUTED)
                text(177, 111, "↑↓←→  /  F X Z C", 11, MUTED)
            if not game.ended:
                undo_hint = "     U  " + tr("undo") if not session or session.allow_undo else ""
                action = tr("place" if source is not None else "select")
                text(177, 129, "Enter  " + action + (undo_hint if source is None else ""), 11)
            if countdown is not None:
                draw.rectangle((5, 139, 315, 164), fill=PANEL)
                text(160, 151, exit_message, 12, ACCENT, "mm")
            else:
                text(177, 147, "Esc  " + tr("unselect" if source is not None else "menu"), 11)
            return image

        if app.page == "lan_help":
            text(14, 7, tr("lan_help"), 18)
            lines = (("双方接入同一局域网，配对时需要联网。",
                      "Zero 和网页均可建房，分享 10 位房间码。",
                      "对手选择「加入房间」，输入房间码。",
                      "房主可指定执红方，并设置是否允许悔棋。",
                      "网页：xiangzero.vercel.app",
                      "若房间允许悔棋，轮到自己时按 U 退两手。") if lang == "zh" else
                     ("Use the same LAN. Pairing requires internet access.", "Host on Zero or the web and share the 10-digit code.",
                      "Choose Join room and enter your opponent's code.",
                      "The host assigns red and can allow undo.",
                      "Web: xiangzero.vercel.app", "If enabled, press U on your turn to undo two moves."))
            for index, line in enumerate(lines):
                text(14, 33 + index * 18, line, 10 if lang == "en" else 12)
            text(14, 151, exit_message if countdown is not None else tr("lan_back"), 11, MUTED)
            return image

        if app.page == "rules_help":
            text(14, 7, tr("rules_help"), 18)
            lines = (("红方先行。按 Enter 选棋，再按 Enter 走棋。",
                      "马有蹩腿，相／象有塞眼且不能过河。",
                      "帅／将、仕／士不可出九宫，双方主将不能照面。",
                      "炮隔一子吃子。兵／卒过河后可横走。",
                      "将死或困毙均判负，单方长将判负。",
                      "三次重复局面时，其他情况判和。") if lang == "zh" else
                     ("Red moves first. Enter selects a piece and then moves it.",
                      "Horses and elephants can be blocked. Elephants stay home.",
                      "Generals and advisors stay in the palace. Generals cannot face.",
                      "Cannons capture over one piece. Soldiers turn after crossing.",
                      "Mate and stalemate lose. One-sided perpetual check loses.",
                      "Other positions repeated three times are drawn."))
            for index, line in enumerate(lines):
                text(14, 33 + index * 18, line, 10 if lang == "en" else 12)
            text(14, 151, exit_message if countdown is not None else "Esc / Enter  " + tr("back"),
                 11, ACCENT if countdown is not None else MUTED)
            return image

        if app.page == "home":
            text(14, 10, tr("menu_title"), 23)
            board(draw, (194, 8, 305, 142), INITIAL, self.font)
            left, right, top, height = 14, 173, 38, 20
        elif app.page == "settings":
            text(14, 7, tr("settings"), 18)
            left, right, top, height = 14, 305, 28, 18
        elif app.page in ("lan", "lan_setup"):
            text(14, 13, tr("lan_host" if app.page == "lan_setup" else "lan"), 19)
            left, right, top, height = 14, 305, 41, 22
        else:
            text(14, 13, tr("replace_title"), 19)
            left, right, top, height = 14, 305, 48, 24

        for index, (key, value) in enumerate(app.menu()):
            y = top + index * height
            active = index == app.selected
            if active:
                draw.rounded_rectangle((left, y, right, y + height - 1), radius=4, fill=PANEL)
                draw.line((left + 2, y + 4, left + 2, y + height - 5), fill=ACCENT, width=2)
            text(left + 9, y + (height - 12) // 2, tr(key), 12, ACCENT if active else TEXT)
            if value:
                text(right - 9, y + (height - 12) // 2, tr(value), 12, MUTED, "rt")

        footer = ("↑↓ / F X    ←→ / Z C  " + tr("change") + "    Esc  " + tr("back")
                  if app.page in ("settings", "lan_setup") else "Enter  " + tr("choose") + "     " + tr("hold_exit"))
        if countdown is not None:
            text(14, 152, exit_message, 11, ACCENT)
            return image
        text(14, 151, tr(app.notice) if app.notice else footer, 11, MUTED)
        return image
