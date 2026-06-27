"""SIGNIFICANT S01E01 — B-ROLL #2 (the median doesn't flinch).
The incomes sort low->high into a line; a marker walks to the exact middle:
MEDIAN = $38,000. Then a whale balloons $4.5M -> $40M; the MEAN marker lurches off
the right edge while the MEDIAN marker doesn't move a pixel.
Caption: 'the median doesn't flinch.'

Render:  env/bin/manim -qh --fps 24 -r 1920,1080 --media_dir /tmp/manim_media 01-scripts/manim_ep1_broll2.py BRoll2
"""
from manim import *

BG = "#0b0e14"
REAL = "#7fb0ff"
WHALE = "#ff5a4d"
INK = "#e9edf5"
MEDc = "#6ad08a"   # median = green, stays
MEANc = "#ffcf56"  # mean = amber, chases

class BRoll2(Scene):
    def construct(self):
        self.camera.background_color = BG
        title = Text("8,100 USERS, SORTED", font="Georgia", color=INK, font_size=34).to_edge(UP, buff=0.6)
        title.set_opacity(0.85)

        axis = Line(LEFT * 5.8, RIGHT * 5.8, color=INK, stroke_width=2).shift(DOWN * 0.2)
        axis.set_opacity(0.6)
        self.play(FadeIn(title), Create(axis), run_time=0.9)

        # a row of dots, sorted low->high (a gentle rising ramp of heights to suggest order)
        n = 41
        xs = [interpolate(axis.get_left()[0] + 0.2, axis.get_right()[0] - 0.2, i / (n - 1)) for i in range(n)]
        base_y = axis.get_center()[1] + 0.12
        dots = [Dot([xs[i], base_y, 0], radius=0.06, color=REAL) for i in range(n)]
        self.play(LaggedStart(*[FadeIn(d, shift=UP * 0.15) for d in dots], lag_ratio=0.02), run_time=1.8)

        mid = n // 2
        # MEDIAN marker walks to the exact middle and stops
        med_line = Line(UP * 0.9, DOWN * 0.5, color=MEDc, stroke_width=5).move_to([xs[0], base_y + 0.2, 0])
        med_lbl = Text("MEDIAN = $38,000", font="Georgia", color=MEDc, font_size=30)
        med_lbl.next_to(med_line, UP, buff=0.15)
        grp = VGroup(med_line, med_lbl)
        self.play(FadeIn(grp), run_time=0.4)
        self.play(grp.animate.move_to([xs[mid], med_line.get_center()[1], 0]),
                  run_time=1.3, rate_func=rate_functions.ease_in_out_sine)
        dots[mid].set_color(MEDc).scale(1.4)
        self.wait(0.4)

        # MEAN marker sits a touch right of median (skewed data)
        mean_x = xs[mid] + 0.5
        mean_line = Line(UP * 0.5, DOWN * 0.9, color=MEANc, stroke_width=5).move_to([mean_x, base_y - 0.2, 0])
        mean_lbl = Text("MEAN", font="Georgia", color=MEANc, font_size=30).next_to(mean_line, DOWN, buff=0.15)
        meang = VGroup(mean_line, mean_lbl)
        self.play(FadeIn(meang), run_time=0.6)
        self.wait(0.4)

        # a whale balloons $4.5M -> $40M : the MEAN lurches off the right edge, MEDIAN doesn't move
        whale = Dot([xs[-1] + 0.1, base_y + 0.0, 0], radius=0.12, color=WHALE)
        whale_lbl = Text("one whale: $4.5M → $40M", font="Georgia", color=WHALE, font_size=26)
        whale_lbl.move_to([3.4, base_y + 1.5, 0])
        self.play(FadeIn(whale, scale=0.4), FadeIn(whale_lbl), run_time=0.5)
        self.play(whale.animate.scale(2.2), run_time=0.5)

        # MEAN chases off-screen right; MEDIAN held in place (emphasise: it does NOT move)
        self.play(
            meang.animate.shift(RIGHT * 9).set_opacity(0.0),     # lurches off the right edge
            Indicate(grp, color=MEDc, scale_factor=1.12),        # median pulses but holds position
            run_time=1.3, rate_func=rate_functions.ease_in_cubic,
        )
        stay = Text("(the median didn't move a pixel)", font="Georgia", color=MEDc, font_size=24, slant=ITALIC)
        stay.move_to([xs[mid], base_y - 1.25, 0])
        self.play(FadeIn(stay), run_time=0.6)
        self.wait(0.5)

        caption = Text("the median doesn't flinch.", font="Georgia", color=INK, font_size=44, slant=ITALIC)
        caption.to_edge(DOWN, buff=0.6)
        self.play(Write(caption), run_time=1.3)
        self.wait(1.6)
