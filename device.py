"""Cardputer Zero framebuffer and keyboard adapters, adapted from WebRadio."""

import ctypes
import mmap
import select
import struct
from array import array
from pathlib import Path

from PIL import Image

from ui import SIZE


class FrameInfo(ctypes.Structure):
    _fields_ = [
        ("id", ctypes.c_char * 16), ("smem_start", ctypes.c_ulong),
        ("smem_len", ctypes.c_uint32), ("type", ctypes.c_uint32),
        ("type_aux", ctypes.c_uint32), ("visual", ctypes.c_uint32),
        ("xpanstep", ctypes.c_uint16), ("ypanstep", ctypes.c_uint16),
        ("ywrapstep", ctypes.c_uint16), ("line_length", ctypes.c_uint32),
        ("mmio_start", ctypes.c_ulong), ("mmio_len", ctypes.c_uint32),
        ("accel", ctypes.c_uint32), ("capabilities", ctypes.c_uint16),
        ("reserved", ctypes.c_uint16 * 2),
    ]


class Framebuffer:
    def __init__(self, path, rotate=False):
        import fcntl

        with open(path, "r+b", buffering=0) as handle:
            variable = struct.unpack("40I", fcntl.ioctl(handle, 0x4600, bytes(160)))
            fixed = FrameInfo.from_buffer_copy(
                fcntl.ioctl(handle, 0x4602, bytes(ctypes.sizeof(FrameInfo))))
            self.width, self.height, _, _, x_offset, y_offset, bits = variable[:7]
            if (self.width, self.height) not in (SIZE, SIZE[::-1]):
                raise ValueError(f"屏幕尺寸为 {self.width}×{self.height}，需要 320×170")
            self.rotation = (
                Image.Transpose.ROTATE_90 if rotate else Image.Transpose.ROTATE_270
            ) if (self.width, self.height) == SIZE[::-1] else (
                Image.Transpose.ROTATE_180 if rotate else None)
            self.channels = [variable[i:i + 3] for i in (8, 11, 14)]
            if (bits not in (16, 24, 32) or fixed.type != 0 or fixed.visual != 2
                    or any(reverse or length < 1 or offset + length > bits
                           for offset, length, reverse in self.channels)):
                raise ValueError("不支持此屏幕的颜色格式")
            self.depth = bits // 8
            self.stride = fixed.line_length
            self.row_bytes = self.width * self.depth
            self.start = y_offset * self.stride + x_offset * self.depth
            end = self.start + (self.height - 1) * self.stride + self.row_bytes
            if x_offset * self.depth + self.row_bytes > self.stride or end > fixed.smem_len:
                raise ValueError("屏幕缓冲区尺寸不正确")
            self.buffer = mmap.mmap(handle.fileno(), fixed.smem_len)
            self.luts = [[(value * ((1 << length) - 1) // 255) << offset
                          for value in range(256)] for offset, length, _ in self.channels]

    def show(self, image):
        if self.rotation is not None:
            image = image.transpose(self.rotation)
        offsets = [offset for offset, _, _ in self.channels]
        if self.depth in (3, 4) and self.channels == [(16, 8, 0), (8, 8, 0), (0, 8, 0)]:
            pixels = image.tobytes("raw", "BGRX" if self.depth == 4 else "BGR")
        elif self.depth == 2:
            red, green, blue = self.luts
            samples = iter(image.tobytes())
            pixels = array("H", (red[r] | green[g] | blue[b]
                                 for r, g, b in zip(samples, samples, samples))).tobytes()
        elif self.depth == 4 and offsets == [0, 8, 16] and all(
                length == 8 for _, length, _ in self.channels):
            pixels = image.tobytes("raw", "RGBX")
        else:
            red, green, blue = self.luts
            pixels = b"".join((red[r] | green[g] | blue[b]).to_bytes(self.depth, "little")
                              for r, g, b in image.getdata())
        if self.stride == self.row_bytes:
            self.buffer[self.start:self.start + len(pixels)] = pixels
        else:
            for row in range(self.height):
                start = self.start + row * self.stride
                src = row * self.row_bytes
                self.buffer[start:start + self.row_bytes] = pixels[src:src + self.row_bytes]

    def close(self):
        self.buffer.close()


def open_keyboard(evdev, path):
    if path:
        return evdev.InputDevice(path)
    for candidate in sorted(Path("/dev/input").glob("event*")):
        try:
            device = evdev.InputDevice(str(candidate))
        except OSError:
            continue
        if "tca8418" in device.name.lower():
            return device
        device.close()
    return evdev.InputDevice("/dev/input/by-path/platform-3f804000.i2c-event")


def run(app, screen, framebuffer, keyboard, rotate):
    import evdev

    keys = open_keyboard(evdev, keyboard)
    try:
        display = Framebuffer(framebuffer, rotate)
        try:
            while app.running:
                events = []
                if select.select([keys.fd], [], [], 0.035)[0]:
                    try:
                        events = list(keys.read())
                    except BlockingIOError:
                        pass
                for event in events:
                    if not app.running:
                        break
                    if event.type == evdev.ecodes.EV_SYN and event.code == evdev.ecodes.SYN_DROPPED:
                        app.cancel_escape()
                    if event.type != evdev.ecodes.EV_KEY:
                        continue
                    key = evdev.ecodes.KEY.get(event.code, "")
                    if isinstance(key, list):
                        key = key[0]
                    key = key.removeprefix("KEY_").lower()
                    if key == "esc" and event.value == 0:
                        app.release_escape()
                    elif event.value in (1, 2):
                        app.handle("escape" if key == "esc" else key, event.value == 2)
                app.tick()
                if app.running and app.dirty:
                    display.show(screen.render(app))
                    app.dirty = False
        finally:
            display.close()
    finally:
        keys.close()


