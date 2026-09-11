#!/usr/bin/env bash
# One-command rebuild of boards/board1.png + boards/board2.png.
# Deterministic (seed=42). Assumes the data/*.json engines have already run
# (see boards/README.md "Upstream"). This script owns the board layer:
# 3D captures -> cells/panels/hero-composite -> compose.
set -e
cd "$(dirname "$0")/.."
PORT=8199
JOB="$(mktemp -u).json"

python -m http.server $PORT >/dev/null 2>&1 &
SRV=$!
cleanup(){ kill $SRV 2>/dev/null || true; rm -f "$JOB"; }
trap cleanup EXIT
sleep 2

cap(){ # name  query
  cat > "$JOB" <<EOF
{ "url":"http://localhost:$PORT/index.html?$2","viewport":[1600,1000],"scale":2,"ready":"window.CAPTURE_READY","shots":[{"name":"$1"}] }
EOF
  python scripts/capture.py "$JOB" boards/captures/3d
}

echo "[1/5] 3D captures (seed=42)…"
# Board 1 — hero + 3 algorithmically-selected detail extremes (worst/peak-congestion/best; seed-stable)
cap b1_hero             "capture=1&cam=hero&colorby=attribution&layers=buildings&bg=dark&ticks=150"
cap b1_detail_worst     "capture=1&cam=detail&s=104.5&colorby=attribution&layers=buildings&bg=dark&ticks=120"
cap b1_detail_congestion "capture=1&cam=detail&s=560.9&colorby=attribution&layers=buildings&bg=dark&ticks=120"
cap b1_detail_best      "capture=1&cam=detail&s=1816.6&colorby=attribution&layers=buildings&bg=dark&ticks=120"
# Board 2 — 4 hero passes (context on dark; glow passes on black for screen-blend)
cap b2_context "capture=1&cam=deck-hero&pass=context&bg=dark&ticks=150"
cap b2_heatmap "capture=1&cam=deck-hero&pass=heatmap&bg=black&ticks=200"
cap b2_trails  "capture=1&cam=deck-hero&pass=trails&bg=black&ticks=1000"
cap b2_access  "capture=1&cam=deck-hero&pass=access&bg=black&ticks=150"

echo "[2/5] behavioural metrics (dwell gap, congestion)…"
python scripts/capture_metrics.py "http://localhost:$PORT/index.html"
kill $SRV 2>/dev/null || true

echo "[3/5] matrix cells + grid…"
python - <<'PY'
import json, numpy as np, scripts.render_cell as rc
d=json.load(open('data/removals.json')); m=d['metadata']; sx=d['s_axis']; sc=d['scenarios']
rc.BASE_SVF=next(s['svf'] for s in sc if s['key']=='baseline'); ds=m['diff_p99']
for s in sc: rc.render_cell(s,sx,m,out=f'boards/captures/cells/{s["key"]}.png',diff_scale=ds)
rc.render_key(m,out='boards/captures/cells/KEY.png',diff_scale=ds)
from PIL import Image
order=['baseline','pre2009','forward','KEY','r1','r2','r3','r4','r5','r6','r7','r8','r9','r10','r11','r12']
cw,ch,gu=640,500,18; G=Image.new('RGB',(4*cw+5*gu,4*ch+5*gu),(10,11,15))
for i,k in enumerate(order):
    im=Image.open(f'boards/captures/cells/{k}.png'); r,c=divmod(i,4); G.paste(im,(gu+c*(cw+gu),gu+r*(ch+gu)))
G.save('boards/captures/_grid16.png')
PY

echo "[4/5] board-2 panels + hero composite…"
python scripts/render_board2.py
python - <<'PY'
from PIL import Image, ImageChops, ImageEnhance
D='boards/captures/3d/'
dim=lambda f,x: ImageEnhance.Brightness(Image.open(D+f).convert('RGB')).enhance(x)
out=Image.open(D+'b2_context.png').convert('RGB')
out=ImageChops.screen(out, dim('b2_heatmap.png',0.95))
out=ImageChops.screen(out, dim('b2_trails.png',0.26))
out=ImageChops.screen(out, dim('b2_access.png',0.40))
out.save(D+'_b2_hero_composite.png')
PY

echo "[5/5] compose boards…"
python scripts/compose_boards.py 1
python scripts/compose_boards.py 2
echo "DONE — boards/board1.png + boards/board2.png (5100x3300 @ 300dpi, seed=42)"
