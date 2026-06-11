#!/bin/bash
# Batch-produce one 2D video per remaining channel: scaffold → auto-script → render.
# Sequential on purpose — ComfyUI (:8188) and MLX (:8000) are shared, single-GPU.
cd /Users/nazeera/Documents/AI_PRODUCER || exit 1
PY=env/bin/python3
UNITS="ambient book-review dev-cloud sarcastic-commentary sarcastic-explainers sarcastic-me translation"

for u in $UNITS; do
  slug="$u"
  echo "============================================================"
  echo "===== CHANNEL: $u  ($(date +%H:%M:%S)) ====="
  echo "============================================================"

  # 1. scaffold the run (skip if it somehow already exists)
  $PY 01_SKILLS/init_project.py create "$slug" --title "$u" 2>&1 | tail -1

  # 2. auto-generate an on-brand script into the run
  $PY 01_SKILLS/generate_channel_script.py deparadigm-media "$u" "$slug" 2>&1 | tail -6

  # 3. full 2D pipeline
  $PY 01_SKILLS/pipeline_orchestrator.py run "$slug" --mode 2d --title "$u" 2>&1 | tail -4
  echo "===== DONE: $u  ($(date +%H:%M:%S)) ====="
done

echo
echo "============================================================"
echo "===== BATCH SUMMARY ====="
echo "============================================================"
for u in $UNITS; do
  m="05_PROJECTS/$u/episodes/EP01/09-deliver/${u}*master.mp4"
  m=$(ls 05_PROJECTS/$u/episodes/EP01/09-deliver/*master.mp4 2>/dev/null | head -1)
  if [ -n "$m" ] && [ -f "$m" ]; then
    info=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$m" 2>/dev/null)
    astream=$(ffprobe -v error -select_streams a -show_entries stream=codec_name -of csv=p=0 "$m" 2>/dev/null)
    plat=$(ls 05_PROJECTS/$u/09-deliver/*_*.mp4 2>/dev/null | wc -l | tr -d ' ')
    echo "  $u: OK — ${info}s, audio=${astream:-NONE}, ${plat} platform cuts"
  else
    echo "  $u: NO MASTER (check pipeline log)"
  fi
done
echo "BATCH_COMPLETE"
