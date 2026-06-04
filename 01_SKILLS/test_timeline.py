import sys
from pathlib import Path

# 1. First, append the root workspace directory to the system path context
# This allows Python to look inside project directories natively
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

# 2. Now that the path is appended, safely import the timeline builder method
from solocorn_media_bridge import generate_fcpxml_timeline

# 3. Gather your freshly rendered video clip assets
movie_assets = [
    "03_ASSETS/normal_curve_scene.mp4",
    "03_ASSETS/empirical_rule_scene.mp4"
]

# 4. Define the export destination path for the NLE project timeline file
output_timeline = "03_ASSETS/_HANDOFF_FCP_CAPCUT/stats_lesson_assembly.fcpxml"

# 5. Execute the compiler sequence
generate_fcpxml_timeline(movie_assets, output_timeline)