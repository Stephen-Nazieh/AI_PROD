import sys
from pathlib import Path

# 1. Align system paths to project root workspace
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

# 2. Append the 01_SKILLS directory explicitly to path context
# This allows us to import 'skills' directly without using the number-prefixed folder path
SKILLS_DIR = PROJECT_ROOT / "01_SKILLS"
sys.path.append(str(SKILLS_DIR))

# 3. Clean import statement bypassing the numeric directory name restriction
try:
    from skills import process_raw_sources
except ImportError as e:
    print(f"❌ Core import map failed. Details: {str(e)}")
    sys.exit(1)

print("🔄 Initializing DeParadigm Media Content Pipeline Ingestion Run...")

# 4. Execute the sweeping clean and compile sequence via the local mlx-lm model
try:
    result_summary = process_raw_sources()
    print("-" * 60)
    print(result_summary)
    print("-" * 60)
    print("✅ Ingestion cycle completed successfully.")
except Exception as e:
    print(f"❌ Ingestion sequence failure. Details: {str(e)}")