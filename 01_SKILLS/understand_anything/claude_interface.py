#!/usr/bin/env python3
import json
import requests
import re
from pathlib import Path


def sanitize_generated_code(raw_response: str) -> str:
    """Strip an LLM code response down to appendable, syntactically-safer Python.

    Pure function (no I/O) so it can be unit-tested directly — AGENTS.md requires
    the sanitizer be validated against ≥3 generated scene classes. Behavior:
      • drops markdown code-fence lines (```), incl. ```python
      • drops loose single-word lines that aren't a call/`self.` (LLM stray tokens)
      • re-indents known nested kwargs (x_range=…, color=…) to 12 spaces
      • seals one dangling '(' per line when the model leaves it unbalanced
    """
    clean_code = ""
    for line in raw_response.splitlines():
        if line.strip().startswith("```"):
            continue
        # Filter out loose single words that break syntax
        if len(line.strip().split()) == 1 and not line.strip().endswith(")") and not line.strip().startswith("self."):
            continue
        # 🛡️ DYNAMIC INDENTATION PASS: align standalone nested args to 12 spaces
        if re.match(r'^\s*(x_range|y_range|axis_config|color|h_buff|v_buff)=', line):
            line = "            " + line.strip()
        # Automatically seal an open parenthesis the model left dangling
        if line.count("(") > line.count(")"):
            line += ")"
        clean_code += line + "\n"
    return clean_code


class ClaudeCodeAutomationBridge:
    """
    Advanced Code Generation Engine with an integrated, aggressive 
    structural auto-formatter to strip accidental local LLM indents.
    """
    def __init__(self, api_base: str = "http://127.0.0.1:8000/v1"):
        self.api_base = api_base
        self.target_file = Path("01_SKILLS/render_scenes.py")

    def execute_agentic_script_generation(self, lesson_topic: str, lesson_summary: str) -> str:
        print(f"🤖 [Code Generator] Compiling ADVANCED vector class for: '{lesson_topic}'...")
        class_name = f"{lesson_topic.replace(' ', '')}Scene"

        system_instruction = (
            "You are a Senior EdTech Engineering core specializing in premium, broadcast-grade Manim animations.\n"
            "You must write a single, complete Python class matching the requested topic. Follow these design rules strictly:\n"
            "1. ALWAYS include a beautifully labeled coordinate system using 'Axes'. Add custom x_range and y_range parameters.\n"
            "2. Use 'MathTex' or 'Tex' for mathematical notation and equations. Make formulas pop with distinct contrast colors (e.g., YELLOW, GREEN).\n"
            "3. Implement fluid animations. Draw graphs using 'axes.plot()'. Animate paths onto the screen using 'Create(graph)' and 'Write(labels)'.\n"
            "4. CRITICAL: For text labels containing mathematical characters, use a raw string literal prefixed with r like: Text(r'As x approaches 0') or use MathTex(r'x \\to 0') with double backslashes.\n"
            "5. CRITICAL: Ensure correct indentation. Inside a class method, every standard line must start with exactly 8 spaces. If a function argument spans multiple lines, align them perfectly.\n"
            "6. ONLY output raw, valid Python code inside a markdown code block. Do not write conversational explanations or text outside the code block."
        )

        user_prompt = f"""
Write an advanced, visually cinematic Manim class named `{class_name}` that provides a deep visual proof/graphical display for this topic: "{lesson_summary}".

Use this standard boilerplate configuration for axis labels:
x_label = axes.get_x_axis_label(MathTex("x"))
y_label = axes.get_y_axis_label(MathTex("y"))
"""

        payload = {
            "model": "mlx-community/Qwen2.5-Coder-7B-Instruct-4bit",
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.2
        }

        try:
            response = requests.post(f"{self.api_base}/chat/completions", json=payload, timeout=45)
            response.raise_for_status()
            raw_response = response.json()['choices'][0]['message']['content']

            clean_code = sanitize_generated_code(raw_response)

            if self.target_file.exists():
                current_content = self.target_file.read_text(encoding="utf-8")
                
                if f"class {class_name}" in current_content:
                    print(f"⏩ [Code Generator] Class '{class_name}' already exists in file scope.")
                    return class_name
                    
                updated_content = current_content.rstrip() + "\n\n\n" + clean_code.strip() + "\n"
                self.target_file.write_text(updated_content, encoding="utf-8")
                print(f"✨ [Code Generator] Advanced class `{class_name}` successfully appended to {self.target_file.name}")
                return class_name
            return None

        except Exception as e:
            print(f"⚠️ [Code Generator] Fallback initiated: {e}")
            fallback_class = (
                f"\n\nclass {class_name}(Scene):\n"
                f"    def construct(self):\n"
                f"        title = Tex(r\"{lesson_topic}\", font_size=40).to_edge(UP)\n"
                f"        axes = Axes(x_range=[-3, 3, 1], y_range=[0, 1, 0.5])\n"
                f"        x_label = axes.get_x_axis_label(\"x\")\n"
                f"        y_label = axes.get_y_axis_label(\"y\")\n"
                f"        self.play(Write(title), Create(axes), Write(x_label), Write(y_label))\n"
                f"        self.wait(2)\n"
            )
            if self.target_file.exists():
                with open(self.target_file, "a", encoding="utf-8") as f:
                    f.write(fallback_class)
                return class_name
            return None