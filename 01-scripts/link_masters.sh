#!/bin/bash
# Idempotently symlink each channel's finished master + platform cuts from its
# 05_PROJECTS run into business_units/<company>/<unit>/assets/ (the studio-model
# home). Re-runnable: relinks with -f, skips channels whose master isn't ready.
cd /Users/nazeera/Documents/AI_PRODUCER || exit 1
CO=deparadigm-media
linked=0; pending=0

abspath() { echo "$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"; }

for u in ap-stats ambient book-review dev-cloud sarcastic-commentary sarcastic-explainers sarcastic-me translation; do
  run=$u; [ "$u" = "ap-stats" ] && run=ap-stats-pilot
  m=$(ls "05_PROJECTS/$run/episodes/EP01/09-deliver/"*master.mp4 2>/dev/null | head -1)
  assets="business_units/$CO/$u/assets"
  if [ -z "$m" ] || [ ! -f "$m" ]; then
    echo "  ⏳ $u — no master yet (run=$run)"; pending=$((pending+1)); continue
  fi
  mkdir -p "$assets"
  ln -sf "$(abspath "$m")" "$assets/${u}_master.mp4"
  c=0
  for cut in "05_PROJECTS/$run/09-deliver/"*_*.mp4; do
    [ -f "$cut" ] || continue
    ln -sf "$(abspath "$cut")" "$assets/$(basename "$cut")"
    c=$((c+1))
  done
  echo "  ✅ $u — master + $c cuts → $assets"
  linked=$((linked+1))
done
echo "LINK_DONE linked=$linked pending=$pending"
