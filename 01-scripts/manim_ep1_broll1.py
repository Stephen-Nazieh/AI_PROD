"""SIGNIFICANT S01E01 — B-ROLL #1 (the show's signature stat-insert).
A dot plot of user incomes builds clustered ~$30-40k; then THREE whale outliers slam
in far right; the x-axis rescales violently to fit them and the real cluster squashes
into a sliver. Caption: 'a few outliers, and the picture lies.'

Render:  env/bin/manim -qh --fps 24 -r 1920,1080 01-scripts/manim_ep1_broll1.py BRoll1
"""
from manim import *

BG = "#0b0e14"
REAL = "#7fb0ff"     # ordinary users
WHALE = "#ff5a4d"    # outliers
INK = "#e9edf5"

class BRoll1(Scene):
    def construct(self):
        self.camera.background_color = BG

        title = Text("USER INCOME", font="Georgia", color=INK, font_size=34).to_edge(UP, buff=0.6)
        title.set_opacity(0.85)

        # horizontal axis
        axis = Line(LEFT * 5.6, RIGHT * 5.6, color=INK, stroke_width=2).shift(DOWN * 0.4)
        axis.set_opacity(0.7)
        x0 = axis.get_left()
        x1 = axis.get_right()
        lbl_lo = Text("$0", font="Georgia", color=INK, font_size=24).next_to(x0, DOWN, buff=0.25)
        lbl_hi = Text("$60k", font="Georgia", color=INK, font_size=24).next_to(x1, DOWN, buff=0.25)
        for m in (lbl_lo, lbl_hi):
            m.set_opacity(0.7)

        self.play(FadeIn(title), Create(axis), FadeIn(lbl_lo), FadeIn(lbl_hi), run_time=1.0)

        # ---- build the real-user dot plot, clustered ~30-40k ----
        # deterministic pseudo-incomes (no RNG): values 26k..46k
        seed = [33, 38, 41, 29, 36, 44, 31, 39, 35, 28, 42, 37, 34, 40, 32, 45,
                30, 43, 36, 38, 33, 41, 35, 29, 39, 37, 31, 44, 34, 40, 36, 32, 38, 42, 35, 30]
        # axis spans $0..$60k over x0..x1
        def xpos(k):  # k in thousands
            return x0[0] + (k / 60.0) * (x1[0] - x0[0])
        base_y = axis.get_center()[1] + 0.12
        buckets = {}
        dots = []
        for k in seed:
            b = round(k / 2) * 2
            lvl = buckets.get(b, 0); buckets[b] = lvl + 1
            d = Dot([xpos(b), base_y + lvl * 0.17, 0], radius=0.07, color=REAL)
            dots.append(d)
        cluster = VGroup(*dots)
        self.play(LaggedStart(*[FadeIn(d, shift=DOWN * 0.25) for d in dots],
                              lag_ratio=0.035), run_time=2.2)

        mean_now = Text("looks like a $30–40k crowd", font="Georgia", color=REAL, font_size=26)
        mean_now.next_to(cluster, UP, buff=0.5)
        self.play(FadeIn(mean_now), run_time=0.7)
        self.wait(0.5)

        # ---- the whales arrive: axis rescales violently, cluster squashes to a sliver ----
        new_hi = Text("$4.5M", font="Georgia", color=WHALE, font_size=24).move_to(lbl_hi)
        # real cluster compresses horizontally into a sliver just right of $0
        cluster_target = cluster.copy()
        cluster_target.stretch_to_fit_width(0.5)
        cluster_target.next_to(x0, UR, buff=0.1).align_to(cluster, DOWN)

        # three whale dots fly in from far right to near the right end
        whales = VGroup(
            Dot([x1[0] - 1.6, base_y + 0.0, 0], radius=0.1, color=WHALE),
            Dot([x1[0] - 0.6, base_y + 0.0, 0], radius=0.1, color=WHALE),
            Dot([x1[0] - 1.0, base_y + 0.0, 0], radius=0.1, color=WHALE),
        )
        whales_start = whales.copy().shift(RIGHT * 4).set_opacity(0)

        self.play(
            Transform(lbl_hi, new_hi),
            FadeOut(mean_now, shift=UP * 0.3),
            Transform(cluster, cluster_target),
            run_time=1.4, rate_func=rate_functions.ease_in_out_sine,
        )
        self.add(whales_start)
        self.play(whales_start.animate.move_to(whales).set_opacity(1.0),
                  run_time=0.8, rate_func=rate_functions.ease_out_back)

        whale_lbl = Text("3 users: $2M–4.5M", font="Georgia", color=WHALE, font_size=26)
        whale_lbl.next_to(whales_start, UP, buff=0.4)
        self.play(FadeIn(whale_lbl), run_time=0.6)

        caption = Text("a few outliers, and the picture lies.",
                       font="Georgia", color=INK, font_size=40, slant=ITALIC).to_edge(DOWN, buff=0.7)
        self.play(Write(caption), run_time=1.4)
        self.wait(1.6)
