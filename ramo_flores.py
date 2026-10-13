from __future__ import annotations

import math
import random
import time
import tkinter as tk
from dataclasses import dataclass


SCENE_WIDTH = 960
SCENE_HEIGHT = 720
DURATION = 9.0
BACKGROUND = "#000000"

GREENS = ("#1b662e", "#237a36", "#2f8b3c", "#3b9948")
LEAF_GREENS = ("#267a35", "#338e3f", "#43a14a", "#5aaf55")
YELLOWS = ("#f2a900", "#fbc31a", "#ffdc35", "#ffe455", "#fff078")
CENTERS = ("#b96b12", "#d88914", "#eaa323", "#f4bd3d", "#ffd45c")


@dataclass(frozen=True)
class Dot:
    when: float
    x: float
    y: float
    size: float
    color: str


@dataclass(frozen=True)
class Flower:
    x: float
    y: float
    radius: float
    rotation: float


FLOWERS = (
    Flower(348, 250, 47, -0.12),
    Flower(435, 221, 48, 0.10),
    Flower(525, 226, 47, -0.06),
    Flower(612, 256, 46, 0.14),
    Flower(301, 326, 46, -0.08),
    Flower(382, 311, 47, 0.06),
    Flower(472, 305, 48, 0.03),
    Flower(559, 315, 47, -0.11),
    Flower(644, 329, 46, 0.08),
    Flower(374, 386, 46, -0.04),
    Flower(478, 383, 48, 0.12),
    Flower(577, 389, 46, -0.07),
)


def quadratic(start, control, end, t):
    """Point on a quadratic Bézier curve."""
    back = 1 - t
    return (
        back * back * start[0] + 2 * back * t * control[0] + t * t * end[0],
        back * back * start[1] + 2 * back * t * control[1] + t * t * end[1],
    )


def add_leaf(dots, rng, origin, direction, length, width, start_time):
    """Scatter points inside a pointed leaf and add a subtle central vein."""
    dx, dy = direction
    norm = math.hypot(dx, dy)
    dx, dy = dx / norm, dy / norm
    px, py = -dy, dx

    for _ in range(85):
        along = rng.random()
        half_width = width * math.sin(math.pi * along) ** 0.85
        across = rng.uniform(-1, 1) * half_width
        curve = 6 * math.sin(math.pi * along)
        x = origin[0] + dx * length * along + px * (across + curve)
        y = origin[1] + dy * length * along + py * (across + curve)
        when = start_time + 0.05 * along + rng.uniform(0, 0.015)
        dots.append(Dot(when, x, y, rng.uniform(1.3, 2.2), rng.choice(LEAF_GREENS)))

    for step in range(16):
        along = step / 15
        curve = 6 * math.sin(math.pi * along)
        x = origin[0] + dx * length * along + px * curve
        y = origin[1] + dy * length * along + py * curve
        dots.append(Dot(start_time + 0.05 * along, x, y, 1.1, "#65bf60"))


def make_stems_and_leaves(dots, rng):
    base = (480, 575)

    for index, flower in enumerate(FLOWERS):
        spread = index - (len(FLOWERS) - 1) / 2
        start = (base[0] + spread * 1.5, base[1] - abs(spread) * 1.3)
        end = (flower.x, flower.y + flower.radius * 0.12)
        control = (
            base[0] + (flower.x - base[0]) * 0.44,
            base[1] - (base[1] - end[1]) * 0.42,
        )

        # Thin, dark stems support the bouquet without competing with the flowers.
        for step in range(145):
            t = step / 144
            x, y = quadratic(start, control, end, t)
            x += rng.gauss(0, 0.85)
            y += rng.gauss(0, 0.85)
            when = max(0, 0.01 + 0.14 * t + rng.uniform(-0.012, 0.012))
            dots.append(Dot(when, x, y, rng.uniform(1.2, 2.1), rng.choice(GREENS)))

        leaf_t = 0.43 + 0.1 * (index % 3)
        origin = quadratic(start, control, end, leaf_t)
        side = -1 if index % 2 == 0 else 1
        direction = (side * 0.95, -0.38)
        leaf_start = 0.035 + 0.14 * leaf_t
        add_leaf(
            dots,
            rng,
            origin,
            direction,
            length=39 + rng.uniform(-4, 6),
            width=10 + rng.uniform(-2, 2),
            start_time=leaf_start,
        )


def make_petals(dots, rng, flower, flower_index):
    petal_count = 12
    center_offset = flower.radius * 0.54
    half_length = flower.radius * 0.48
    half_width = flower.radius * 0.17

    for petal_index in range(petal_count):
        angle = flower.rotation + 2 * math.pi * petal_index / petal_count
        along_x, along_y = math.cos(angle), math.sin(angle)
        across_x, across_y = -along_y, along_x

        for _ in range(72):
            # Uniform sample in an ellipse. Individual dots, rather than a
            # filled polygon, create the soft, granular silhouette.
            theta = rng.uniform(0, 2 * math.pi)
            distance = math.sqrt(rng.random())
            longitudinal = distance * math.cos(theta) * half_length
            lateral = distance * math.sin(theta) * half_width
            x = flower.x + along_x * (center_offset + longitudinal) + across_x * lateral
            y = flower.y + along_y * (center_offset + longitudinal) + across_y * lateral
            when = 0.20 + rng.random() * 0.52 + flower_index * 0.002
            shade = rng.choices(YELLOWS, weights=(1, 3, 5, 3, 1), k=1)[0]
            dots.append(Dot(when, x, y, rng.uniform(1.45, 3.0), shade))

        # A few brighter points sharpen the outer end of each petal.
        for _ in range(10):
            tip = center_offset + half_length * rng.uniform(0.65, 1.02)
            lateral = rng.gauss(0, half_width * 0.22)
            x = flower.x + along_x * tip + across_x * lateral
            y = flower.y + along_y * tip + across_y * lateral
            dots.append(Dot(0.43 + rng.random() * 0.35, x, y, 1.7, "#ffe969"))


def make_center(dots, rng, flower):
    radius = flower.radius * 0.23
    for _ in range(180):
        angle = rng.uniform(0, 2 * math.pi)
        distance = math.sqrt(rng.random()) * radius
        x = flower.x + math.cos(angle) * distance
        y = flower.y + math.sin(angle) * distance
        shade = rng.choices(CENTERS, weights=(1, 3, 5, 3, 1), k=1)[0]
        dots.append(Dot(0.69 + rng.random() * 0.25, x, y, rng.uniform(1.4, 2.9), shade))

    # Sparse highlights make the golden centers read as rounded, not flat.
    for _ in range(24):
        angle = rng.uniform(0, 2 * math.pi)
        distance = math.sqrt(rng.random()) * radius * 0.75
        x = flower.x + math.cos(angle) * distance - radius * 0.15
        y = flower.y + math.sin(angle) * distance - radius * 0.15
        dots.append(Dot(0.85 + rng.random() * 0.13, x, y, 1.5, "#ffe78a"))


def build_bouquet():
    rng = random.Random(20260921)
    dots = []
    make_stems_and_leaves(dots, rng)
    for index, flower in enumerate(FLOWERS):
        make_petals(dots, rng, flower, index)
        make_center(dots, rng, flower)
    return sorted(dots, key=lambda dot: dot.when)


def main():
    root = tk.Tk()
    root.title("Ramo de flores amarillas")
    root.configure(bg=BACKGROUND)

    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    width = min(SCENE_WIDTH, max(500, screen_width - 80))
    height = min(SCENE_HEIGHT, max(400, screen_height - 100))
    left = max(0, (screen_width - width) // 2)
    top = max(0, (screen_height - height) // 2)
    root.geometry(f"{width}x{height}+{left}+{top}")
    root.resizable(False, False)
    root.bind("<Escape>", lambda _event: root.destroy())

    canvas = tk.Canvas(root, bg=BACKGROUND, highlightthickness=0, bd=0)
    canvas.pack(fill="both", expand=True)

    scale = min(width / SCENE_WIDTH, height / SCENE_HEIGHT)
    shift_x = (width - SCENE_WIDTH * scale) / 2
    shift_y = (height - SCENE_HEIGHT * scale) / 2
    dots = build_bouquet()
    next_dot = 0
    started = time.monotonic()

    def draw_frame():
        nonlocal next_dot
        elapsed = min(1.0, (time.monotonic() - started) / DURATION)
        while next_dot < len(dots) and dots[next_dot].when <= elapsed:
            dot = dots[next_dot]
            x = shift_x + dot.x * scale
            y = shift_y + dot.y * scale
            radius = max(0.7, dot.size * scale / 2)
            canvas.create_oval(
                x - radius,
                y - radius,
                x + radius,
                y + radius,
                fill=dot.color,
                outline="",
            )
            next_dot += 1

        if next_dot < len(dots):
            root.after(20, draw_frame)

    root.after(20, draw_frame)
    root.mainloop()


if __name__ == "__main__":
    main()
