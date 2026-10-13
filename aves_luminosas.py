from __future__ import annotations

import math
from pathlib import Path
import sys
import time
from dataclasses import dataclass


SCENE_WIDTH = 960
SCENE_HEIGHT = 720
REFERENCE_SIZE = (736, 723)
BACKGROUND = "#000000"
INITIAL_PAUSE = 0.12
BIRD_DURATION = 2.6
BIRD_OVERLAP = 0.35
BIRD_INTERVAL = BIRD_DURATION - BIRD_OVERLAP
DURATION = INITIAL_PAUSE + BIRD_DURATION + 2 * BIRD_INTERVAL
FRAME_MS = 25


IMAGE_PATH = Path(__file__).resolve().with_name("birds_mejoradas.png")
ORIGINAL_IMAGE_PATH = Path(__file__).resolve().with_name("birds.jpg")


BIRD_SHAPES = (
    ((176, 379),
     ((97, 325), (155, 282), (247, 219), (309, 232), (359, 213),
      (383, 279), (328, 350), (275, 391), (249, 426), (261, 477),
      (259, 551), (200, 553), (180, 487), (119, 429), (94, 382))),
    ((479, 306),
     ((397, 261), (425, 215), (434, 141), (459, 83), (533, 85),
      (565, 149), (573, 261), (601, 321), (681, 363), (690, 422),
      (622, 443), (548, 396), (490, 367), (434, 331), (394, 307))),
    ((430, 461),
     ((264, 435), (355, 428), (397, 382), (458, 388), (508, 439),
      (554, 494), (581, 573), (501, 588), (467, 543), (400, 552),
      (292, 537), (239, 491), (242, 451))),
)


@dataclass(frozen=True)
class BirdLayer:
    light: object
    distance: object
    start: float


def load_pillow():
    """Import lazily so even a missing dependency produces a useful message."""
    try:
        from PIL import Image, ImageChops, ImageDraw, ImageFilter
    except ImportError as exc:
        raise RuntimeError(
            "python -m pip install -r requirements.txt"
        ) from exc
    return Image, ImageChops, ImageDraw, ImageFilter


def bird_progress(elapsed: float, start: float) -> float:
    if elapsed >= start + BIRD_DURATION:
        return 1.0
    return max(0.0, min(1.0, (elapsed - start) / BIRD_DURATION))


def reveal_front(progress: float) -> float:
    return -10 + max(0.0, min(1.0, progress)) * 275


def fit_scene(screen_width: int, screen_height: int) -> tuple[int, int]:
    available_width = max(1, screen_width - 80)
    available_height = max(1, screen_height - 100)
    scale = min(1.0, available_width / SCENE_WIDTH,
                available_height / SCENE_HEIGHT)
    return max(1, round(SCENE_WIDTH * scale)), max(1, round(SCENE_HEIGHT * scale))


def build_birds(path: Path | None = None) -> tuple[tuple[int, int], list[BirdLayer]]:
    Image, ImageChops, ImageDraw, ImageFilter = load_pillow()
    if path is None:
        path = IMAGE_PATH if IMAGE_PATH.is_file() else ORIGINAL_IMAGE_PATH
    try:
        with Image.open(path) as source:
            gray = source.convert("L")
    except FileNotFoundError as exc:
        raise RuntimeError(f"No se encontró la imagen:\n{path}") from exc
    except OSError as exc:
        raise RuntimeError(f"No se pudo leer la imagen:\n{path}\n{exc}") from exc

    width, height = gray.size
    sx, sy = width / REFERENCE_SIZE[0], height / REFERENCE_SIZE[1]
    if Path(path).resolve() == ORIGINAL_IMAGE_PATH:
        gray = Image.blend(gray, gray.filter(ImageFilter.MedianFilter(3)), 0.35)
        smoothing = 0.65
    else:
        smoothing = 0.25
    gray = gray.filter(ImageFilter.GaussianBlur(smoothing * min(sx, sy)))
    tones = []
    for value in range(256):
        strength = max(0.0, min(1.0, (value - 22) / 215))
        tones.append(min(255, round(255 * strength ** 1.12 * 1.09)))
    cleaned = gray.point(tones)
    birds = []

    for index, (origin, polygon) in enumerate(BIRD_SHAPES):
        mask = Image.new("L", gray.size)
        ImageDraw.Draw(mask).polygon(
            [(round(x * sx), round(y * sy)) for x, y in polygon], fill=255,
        )
        mask = mask.filter(ImageFilter.GaussianBlur(3 * min(sx, sy)))
        light = ImageChops.multiply(cleaned, mask)
        bounds = light.getbbox()
        if bounds is None:
            raise RuntimeError("La imagen no contiene las aves esperadas.")
        ox, oy = origin[0] * sx, origin[1] * sy
        pixels = light.load()
        maximum = 1.0
        for y in range(bounds[1], bounds[3]):
            for x in range(bounds[0], bounds[2]):
                if pixels[x, y] >= 8:
                    maximum = max(maximum, math.hypot((x - ox) / sx, (y - oy) / sy))
        distances = bytearray([255]) * (width * height)
        for y in range(bounds[1], bounds[3]):
            for x in range(bounds[0], bounds[2]):
                radius = math.hypot((x - ox) / sx, (y - oy) / sy)
                distances[y * width + x] = min(255, round(radius / maximum * 238))
        field = Image.frombytes("L", gray.size, bytes(distances))
        start = INITIAL_PAUSE + index * BIRD_INTERVAL
        birds.append(BirdLayer(light, field, start))
    return gray.size, birds


class Renderer:
    """Downsample once with antialiasing; animate in display resolution."""

    def __init__(self, source_size, birds, window_size):
        self.Image, self.ImageChops, _, self.ImageFilter = load_pillow()
        self.window_size = window_size
        width, height = window_size
        scale = min(width / source_size[0], height / source_size[1])
        self.art_size = (max(1, round(source_size[0] * scale)),
                         max(1, round(source_size[1] * scale)))
        self.offset = ((width - self.art_size[0]) // 2,
                       (height - self.art_size[1]) // 2)
        self.source_size = self.art_size
        self.birds = [BirdLayer(
            bird.light.resize(self.art_size, self.Image.Resampling.LANCZOS),
            bird.distance.resize(self.art_size, self.Image.Resampling.BILINEAR),
            bird.start,
        ) for bird in birds]
        self.blur_scale = min(self.art_size[0] / REFERENCE_SIZE[0],
                              self.art_size[1] / REFERENCE_SIZE[1])
        self.reset()

    def reset(self):
        self.completed = self.Image.new("L", self.source_size)
        self.completed_count = 0

    def glow(self, core):
        near = core.filter(self.ImageFilter.GaussianBlur(3.5 * self.blur_scale))
        far = core.filter(self.ImageFilter.GaussianBlur(11 * self.blur_scale))
        near = near.point([round(value * 0.17) for value in range(256)])
        far = far.point([round(value * 0.10) for value in range(256)])
        return self.ImageChops.add(self.ImageChops.add(core, near), far)

    def render(self, elapsed):
        core = self.completed.copy()
        for index, bird in enumerate(self.birds):
            progress = bird_progress(elapsed, bird.start)
            if index < self.completed_count:
                continue
            if progress >= 1.0:
                self.completed = self.ImageChops.add(self.completed, bird.light)
                self.completed_count += 1
                core = self.completed.copy()
                continue
            if progress <= 0.0:
                break

            front = reveal_front(progress)
            reveal = []
            highlight = []
            for value in range(256):
                amount = max(0.0, min(1.0, (front - value + 10) / 20))
                amount = amount * amount * (3 - 2 * amount)
                reveal.append(round(255 * amount))
                pulse = math.exp(-((value - front + 5) / 8) ** 2)
                highlight.append(round(255 * pulse * 0.19 * math.sin(math.pi * progress)))
            visible = self.ImageChops.multiply(bird.light, bird.distance.point(reveal))
            edge = self.ImageChops.multiply(bird.light, bird.distance.point(highlight))
            core = self.ImageChops.add(core, self.ImageChops.add(visible, edge))

        art = self.glow(core)
        frame = self.Image.new("RGB", self.window_size, BACKGROUND)
        frame.paste(art.convert("RGB"), self.offset)
        return frame


def main() -> int:
    root = None
    try:
        source_size, birds = build_birds()
        try:
            import tkinter as tk
            from PIL import ImageTk
        except ImportError as exc:
            raise RuntimeError("Este Python necesita Tkinter para abrir la ventana.") from exc

        root = tk.Tk()
        root.title("Aves de luz · R para repetir · Esc para cerrar")
        root.configure(bg=BACKGROUND)
        screen_width, screen_height = root.winfo_screenwidth(), root.winfo_screenheight()
        width, height = fit_scene(screen_width, screen_height)
        left, top = max(0, (screen_width - width) // 2), max(0, (screen_height - height) // 2)
        root.geometry(f"{width}x{height}+{left}+{top}")
        root.resizable(False, False)
        canvas = tk.Canvas(root, bg=BACKGROUND, highlightthickness=0, bd=0)
        canvas.pack(fill="both", expand=True)
        renderer = Renderer(source_size, birds, (width, height))
        photo = ImageTk.PhotoImage(renderer.render(0), master=root)
        canvas.create_image(0, 0, anchor="nw", image=photo)
        timer = None
        started = 0.0

        def draw_frame():
            nonlocal timer
            timer = None
            elapsed = time.monotonic() - started
            photo.paste(renderer.render(elapsed))
            if elapsed < DURATION:
                timer = root.after(FRAME_MS, draw_frame)

        def restart(_event=None):
            nonlocal started, timer
            if timer is not None:
                root.after_cancel(timer)
                timer = None
            renderer.reset()
            started = time.monotonic()
            draw_frame()

        def close(_event=None):
            nonlocal timer
            if timer is not None:
                root.after_cancel(timer)
                timer = None
            root.destroy()

        root.bind("<Escape>", close)
        root.bind("<r>", restart)
        root.bind("<R>", restart)
        root.bind("<space>", restart)
        root.protocol("WM_DELETE_WINDOW", close)
        root.after_idle(restart)
        root.mainloop()
        return 0
    except Exception as exc:
        print(f"No se pudo abrir Aves de luz:\n{exc}", file=sys.stderr)
        if root is not None:
            try:
                root.destroy()
            except Exception:
                pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
