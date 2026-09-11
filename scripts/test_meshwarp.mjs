// Synthetic sanity tests for meshWarp.js — run: node scripts/test_meshwarp.mjs
// Three cases: uniform-neutral (no distortion), single hotspot (local
// symmetric expansion), single coldspot (local symmetric compression).

import { buildGrid, relaxMesh, warpFactor, foldedCells, neutralENorm, WARP_MIN, WARP_MAX } from '../meshWarp.js';

const SIZE = 400, N = 41;                     // 400 m box, 41×41 grid (10 m cells)
const CX = SIZE / 2, CZ = SIZE / 2, R = 90;   // synthetic spot radius
const NEUTRAL = neutralENorm();               // eNorm where warpFactor === 1
console.log(`[params] warpFactor range ×${WARP_MIN}–×${WARP_MAX}, neutral eNorm ${NEUTRAL.toFixed(4)}`);

function solve(eNormAt) {
  const grid = buildGrid(0, 0, SIZE, SIZE, N, N);
  const wf = new Float64Array(N * N);
  for (let i = 0; i < N * N; i++) {
    const x = grid.truePos[2 * i], z = grid.truePos[2 * i + 1];
    const d = Math.hypot(x - CX, z - CZ);
    const influence = Math.max(0, 1 - d / R);
    wf[i] = warpFactor(eNormAt(d), influence);
  }
  const out = relaxMesh(grid, wf, { iterations: 900 });
  return { grid, wf, ...out };
}

function stats(grid, pos) {
  const n = grid.rows * grid.cols;
  let maxD = 0, sum = 0;
  for (let i = 0; i < n; i++) {
    const d = Math.hypot(pos[2 * i] - grid.truePos[2 * i], pos[2 * i + 1] - grid.truePos[2 * i + 1]);
    if (d > maxD) maxD = d;
    sum += d;
  }
  return { maxDisp: maxD, meanDisp: sum / n };
}

// area of the central 4 cells relative to true
function centerAreaRatio(grid, pos) {
  const c = (N - 1) / 2, cols = grid.cols;
  const quad = (P, r0, c0) => {
    const i00 = r0 * cols + c0, i10 = i00 + 1, i01 = i00 + cols, i11 = i01 + 1;
    const xs = [P[2 * i00], P[2 * i10], P[2 * i11], P[2 * i01]];
    const zs = [P[2 * i00 + 1], P[2 * i10 + 1], P[2 * i11 + 1], P[2 * i01 + 1]];
    let a = 0;
    for (let k = 0; k < 4; k++) a += xs[k] * zs[(k + 1) % 4] - xs[(k + 1) % 4] * zs[k];
    return Math.abs(a / 2);
  };
  let t = 0, w = 0;
  for (const [r0, c0] of [[c - 1, c - 1], [c - 1, c], [c, c - 1], [c, c]]) {
    t += quad(grid.truePos, r0, c0);
    w += quad(pos, r0, c0);
  }
  return w / t;
}

// symmetry: displacement magnitude should match under 90° rotation about center
function symmetryError(grid, pos) {
  const cols = grid.cols, c = (N - 1) / 2;
  let worst = 0;
  for (let r = 0; r < N; r++) {
    for (let cc = 0; cc < N; cc++) {
      const i = r * cols + cc;
      const rr = c + (cc - c), cc2 = c - (r - c);      // rotate 90° in index space
      const j = rr * cols + cc2;
      if (rr < 0 || rr >= N || cc2 < 0 || cc2 >= N) continue;
      const di = Math.hypot(pos[2 * i] - grid.truePos[2 * i], pos[2 * i + 1] - grid.truePos[2 * i + 1]);
      const dj = Math.hypot(pos[2 * j] - grid.truePos[2 * j], pos[2 * j + 1] - grid.truePos[2 * j + 1]);
      worst = Math.max(worst, Math.abs(di - dj));
    }
  }
  return worst;
}

function boundaryMax(grid, pos) {
  let m = 0;
  for (let r = 0; r < N; r++) {
    for (const cc of [0, N - 1]) {
      for (const i of [r * N + cc, cc * N + r]) {
        const d = Math.hypot(pos[2 * i] - grid.truePos[2 * i], pos[2 * i + 1] - grid.truePos[2 * i + 1]);
        if (d > m) m = d;
      }
    }
  }
  return m;
}

let fail = 0;
const check = (name, cond, detail) => {
  console.log(`  ${cond ? 'PASS' : 'FAIL'}  ${name}${detail ? ' — ' + detail : ''}`);
  if (!cond) fail++;
};

// ── Test 1: uniform neutral exposure → near-zero distortion ──────
{
  const r = solve(() => NEUTRAL);
  const s = stats(r.grid, r.pos);
  console.log('[test 1] uniform neutral exposure (warpFactor = 1 everywhere)');
  check('converges to true positions', s.maxDisp < 0.01, `max disp ${s.maxDisp.toExponential(2)} m`);
  check('no folds', foldedCells(r.grid, r.pos) === 0);
}

// ── Test 2: central high-exposure hotspot → local symmetric expansion ──
{
  const r = solve(d => (d < R ? 1.0 : NEUTRAL));
  const s = stats(r.grid, r.pos);
  const ratio = centerAreaRatio(r.grid, r.pos);
  console.log('[test 2] central hotspot (eNorm 1 inside 90 m, neutral outside)');
  check('center expands', ratio > 1.3, `center-cell area ×${ratio.toFixed(3)}`);
  check('symmetric', symmetryError(r.grid, r.pos) < 0.1, `worst 90°-rotation asymmetry ${symmetryError(r.grid, r.pos).toExponential(2)} m`);
  check('no folds', foldedCells(r.grid, r.pos) === 0);
  check('boundary stays anchored', boundaryMax(r.grid, r.pos) < 2.0, `boundary max disp ${boundaryMax(r.grid, r.pos).toFixed(3)} m`);
  console.log(`  info: mesh max displacement ${s.maxDisp.toFixed(2)} m, iterations ${r.iterations}`);
}

// ── Test 3: central low-exposure zone → local symmetric compression ──
{
  const r = solve(d => (d < R ? 0.0 : NEUTRAL));
  const ratio = centerAreaRatio(r.grid, r.pos);
  console.log('[test 3] central coldspot (eNorm 0 inside 90 m, neutral outside)');
  check('center compresses', ratio < 0.7, `center-cell area ×${ratio.toFixed(3)}`);
  check('symmetric', symmetryError(r.grid, r.pos) < 0.1, `worst asymmetry ${symmetryError(r.grid, r.pos).toExponential(2)} m`);
  check('no folds', foldedCells(r.grid, r.pos) === 0);
}

console.log(fail === 0 ? '\nALL MESH TESTS PASS' : `\n${fail} CHECK(S) FAILED`);
process.exit(fail === 0 ? 0 : 1);
