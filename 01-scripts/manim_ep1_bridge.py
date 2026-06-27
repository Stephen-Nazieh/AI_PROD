"""SIGNIFICANT S01E01 — ACT TWO close: Maya rebuilds the slide.
"$92,000" gets struck through and dissolves into "TYPICAL USER $38,000 — the number
you can trust." A visual rhyme with the cold-open slide; the correction made literal.

Render: env/bin/manim -qh --fps 24 -r 1920,1080 --media_dir /tmp/manim_media 01-scripts/manim_ep1_bridge.py Bridge
"""
from manim import *

BG = "#0b0e14"
AMBER = "#ffcf56"
GREENB = "#9fe8c0"
INK = "#e9edf5"

class Bridge(Scene):
    def construct(self):
        self.camera.background_color = BG
        hdr = Text("AVG USER INCOME", font="Georgia", color="#9fb4dd", font_size=40).shift(UP * 1.4)
        big = Text("$92,000", font="Georgia", color=AMBER, font_size=130).next_to(hdr, DOWN, buff=0.4)
        self.play(FadeIn(hdr), FadeIn(big), run_time=0.9)
        self.wait(0.4)

        # strike it through
        strike = Line(big.get_left() + LEFT * 0.1, big.get_right() + RIGHT * 0.1, color="#ff5a4d", stroke_width=8)
        self.play(Create(strike), run_time=0.5)
        self.play(big.animate.set_opacity(0.35), strike.animate.set_opacity(0.6), run_time=0.4)
        self.wait(0.3)

        # dissolve into the corrected slide
        nhdr = Text("TYPICAL USER", font="Georgia", color="#9fb4dd", font_size=40).shift(UP * 1.6)
        nbig = Text("$38,000", font="Georgia", color=GREENB, font_size=130).next_to(nhdr, DOWN, buff=0.4)
        sub = Text("the number you can trust", font="Georgia", color=INK, font_size=38, slant=ITALIC).next_to(nbig, DOWN, buff=0.5)
        self.play(
            FadeOut(big, shift=DOWN * 0.4), FadeOut(strike, shift=DOWN * 0.4),
            ReplacementTransform(hdr, nhdr), FadeIn(nbig, shift=UP * 0.3),
            run_time=1.1,
        )
        self.play(Write(sub), run_time=1.1)
        self.wait(1.8)
