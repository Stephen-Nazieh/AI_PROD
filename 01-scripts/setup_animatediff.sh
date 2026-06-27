#!/bin/bash
# Install ComfyUI-AnimateDiff-Evolved + fetch the SD1.5 motion module and a base
# SD1.5 checkpoint (AnimateDiff v1.5 motion modules are SD1.5-based; our only
# checkpoints are SDXL/Flux, which the v1.5 motion module can't drive).
set -u
cd /Users/nazeera/Documents/AI_PRODUCER/ComfyUI || exit 1
NODES=custom_nodes
MM=models/animatediff_models
CKPT=models/checkpoints
mkdir -p "$MM" "$CKPT"

echo "=== 1. clone AnimateDiff-Evolved node ==="
if [ ! -d "$NODES/ComfyUI-AnimateDiff-Evolved" ]; then
  git clone --depth 1 https://github.com/Kosinkadink/ComfyUI-AnimateDiff-Evolved.git \
    "$NODES/ComfyUI-AnimateDiff-Evolved" 2>&1 | tail -3
else
  echo "  already present"
fi
# VideoHelperSuite gives the frame-load/combine nodes commonly paired with it
if [ ! -d "$NODES/ComfyUI-VideoHelperSuite" ]; then
  git clone --depth 1 https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git \
    "$NODES/ComfyUI-VideoHelperSuite" 2>&1 | tail -3
fi

dl() {  # url dest
  local url="$1" dest="$2"
  if [ -f "$dest" ]; then echo "  exists: $(basename "$dest")"; return 0; fi
  echo "  downloading $(basename "$dest") ..."
  curl -fL --retry 3 -C - -o "${dest}.part" "$url" && mv "${dest}.part" "$dest" \
    && echo "  OK $(du -h "$dest" | cut -f1) $(basename "$dest")" \
    || echo "  FAILED $(basename "$dest")"
}

echo "=== 2. motion module (mm_sd_v15_v2, ~1.7GB) ==="
dl "https://huggingface.co/guoyww/animatediff/resolve/main/mm_sd_v15_v2.ckpt" \
   "$MM/mm_sd_v15_v2.ckpt"

echo "=== 3. SD1.5 toon base (DreamShaper 8, ~2GB) ==="
dl "https://huggingface.co/Lykon/DreamShaper/resolve/main/DreamShaper_8_pruned.safetensors" \
   "$CKPT/dreamshaper_8.safetensors"
# fallback: SD1.5 base if the toon model URL fails
if [ ! -f "$CKPT/dreamshaper_8.safetensors" ]; then
  echo "  toon model unavailable — falling back to SD1.5 base"
  dl "https://huggingface.co/stable-diffusion-v1-5/stable-diffusion-v1-5/resolve/main/v1-5-pruned-emaonly.safetensors" \
     "$CKPT/sd_v1-5.safetensors"
fi

echo "ANIMATEDIFF_SETUP_DONE"
ls -lh "$MM" "$CKPT" 2>/dev/null | grep -iE "\.ckpt|\.safetensors"
