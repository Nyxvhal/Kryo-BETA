#!/usr/bin/env sh
# Kryo - optional AI module (Real-ESRGAN upscaling, RIFE smooth motion).
# Usage: sh setup-ai.sh [auto|cpu|cu118|cu126|cu128]   (default: auto)
set -eu
cd "$(dirname "$0")"
[ -x .ai-venv/bin/python ] || python3 -m venv .ai-venv
.ai-venv/bin/python -m pip install --upgrade pip
flavor="${1:-auto}"
if [ "$flavor" = auto ]; then
  if command -v nvidia-smi >/dev/null 2>&1; then flavor=cu126; else flavor=cpu; fi
fi
echo "PyTorch build: $flavor"
.ai-venv/bin/python -m pip install torch --index-url "https://download.pytorch.org/whl/$flavor"
.ai-venv/bin/python -m pip install -r requirements-ai.txt
.ai-venv/bin/python -c "import torch; print('torch', torch.__version__, '| CUDA:', torch.cuda.is_available())"
echo 'AI module installed. Return to the player and press "Check again". Models download when first needed.'
