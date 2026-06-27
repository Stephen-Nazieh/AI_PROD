"""SIGNIFICANT S01E01 — B-ROLL #3 (the pitch's proof: mean vs median, side by side).
Split screen — LEFT "Mean $92k" with three glowing whales dragging it up; RIGHT
"Median $38k" with the middle user highlighted. Then a z-score flicker on a whale:
"z ≈ +14 — 14 standard deviations from typical. Not your market."

Render:  env/bin/manim -qh --fps 24 -r 1920,1080 --media_dir /tmp/manim_media 01-scripts/manim_ep1_broll3.py BRoll3
"""
from manim import *

BG = "#0b0e14"
REAL = "#7fb0ff"
WHALE = "#ff5a4d"
INK = "#e9edf5"
MEANc = "#ffcf56"
MEDc = "#6ad08a"

class BRoll3(Scene):
    def construct(self):
        self.camera.background_color = BG
        divider = DashedLine(UP * 3.6, DOWN * 3.6, color=INK, stroke_width=2).set_opacity(0.4)

        # ---- LEFT: the MEAN ----
        lhead = Text("MEAN", font="Georgia", color=MEANc, font_size=40).move_to([-3.5, 3.0, 0])
        lval = Text("$92,000", font="Georgia", color=MEANc, font_size=64).next_to(lhead, DOWN, buff=0.2)
        laxis = Line(LEFT * 6.3, LEFT * 0.7, color=INK, stroke_width=2).shift(DOWN * 0.6).set_opacity(0.5)
        # a small ordinary cluster + three glowing whales pulling right
        cluster = VGroup(*[Dot([-5.4 + 0.16 * i, -0.48 + 0.18 * (i % 3), 0], radius=0.05, color=REAL) for i in range(15)])
        whales = VGroup(*[Dot([x, -0.48, 0], radius=0.13, color=WHALE) for x in (-1.5, -1.1, -0.8)])
        lcap = Text("three whales drag it up", font="Georgia", color=WHALE, font_size=26).move_to([-3.5, -1.7, 0])

        # ---- RIGHT: the MEDIAN ----
        rhead = Text("MEDIAN", font="Georgia", color=MEDc, font_size=40).move_to([3.5, 3.0, 0])
        rval = Text("$38,000", font="Georgia", color=MEDc, font_size=64).next_to(rhead, DOWN, buff=0.2)
        raxis = Line(RIGHT * 0.7, RIGHT * 6.3, color=INK, stroke_width=2).shift(DOWN * 0.6).set_opacity(0.5)
        rdots = VGroup(*[Dot([0.9 + 0.30 * i, -0.6, 0], radius=0.06, color=REAL) for i in range(18)])
        midi = 9
        rdots[midi].set_color(MEDc).scale(1.5)
        rmark = Line(UP * 0.4, DOWN * 0.4, color=MEDc, stroke_width=4).move_to(rdots[midi].get_center())
        rcap = Text("the user in the middle", font="Georgia", color=MEDc, font_size=26).move_to([3.5, -1.7, 0])

        self.play(Create(divider), run_time=0.6)
        self.play(FadeIn(lhead), FadeIn(lval), Create(laxis), FadeIn(rhead), FadeIn(rval), Create(raxis), run_time=1.0)
        self.play(LaggedStart(*[FadeIn(d) for d in cluster], lag_ratio=0.04),
                  LaggedStart(*[FadeIn(d) for d in rdots], lag_ratio=0.04), run_time=1.4)
        self.play(FadeIn(whales, scale=0.5), FadeIn(rmark), run_time=0.5)
        self.play(Indicate(whales, color=WHALE, scale_factor=1.3),
                  Indicate(VGroup(rdots[midi], rmark), color=MEDc, scale_factor=1.2), run_time=1.0)
        self.play(FadeIn(lcap, shift=UP * 0.2), FadeIn(rcap, shift=UP * 0.2), run_time=0.6)
        self.wait(0.5)

        # ---- z-score flicker on a whale ----
        zbox = SurroundingRectangle(whales[0], color=WHALE, buff=0.12, stroke_width=3)
        zlbl = Text("z ≈ +14", font="Georgia", color=WHALE, font_size=44).move_to([-3.5, 1.2, 0])
        self.play(Create(zbox), FadeIn(zlbl, scale=1.2), run_time=0.7)
        for _ in range(2):
            self.play(zbox.animate.set_opacity(0.2), run_time=0.12)
            self.play(zbox.animate.set_opacity(1.0), run_time=0.12)
        ztext = Text("14 standard deviations from typical.\nNot your market.",
                     font="Georgia", color=INK, font_size=34, line_spacing=0.8, slant=ITALIC)
        ztext.to_edge(DOWN, buff=0.55)
        self.play(Write(ztext), run_time=1.4)
        self.wait(1.6)
