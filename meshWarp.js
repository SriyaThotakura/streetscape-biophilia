// meshWarp.js — mesh-relaxation cartogram solver (plain ES module, no deps).
//
// A regular grid of vertices covers the site. Each grid edge gets a target
// rest-length = trueLength × warpFactor, where warpFactor > 1 expands
// (high biophilic exposure earns more page space, carbonmap-style) and < 1
// compresses (enclosed, low-exposure stretches). Jacobi spring relaxation
// moves vertices toward those rest-lengths; a weak per-vertex anchor toward
// the true position prevents drift and keeps zero-influence regions (beyond
// the influence radius, or coverage:"none") honestly close to true geometry.
//
// Unit tests: scripts/test_meshwarp.mjs (run `node scripts/test_meshwarp.mjs`).

export const WARP_MIN = 0.3;   // rest-length factor at exposure 0 (compress)
export const WARP_MAX = 1.9;   // rest-length factor at exposure 1 (expand) —
                               // 2.8 and 2.2 fold the hotspot test; 1.9 is
                               // the stable ceiling with current shear springs
export const WARP_GAMMA = 1.6; // gain-curve exponent — pushes mids toward extremes

// Symmetric gain curve: x^γ below the midpoint, mirrored above it, so
// mid-range exposure differences spread toward the extremes instead of
// clustering around warpFactor 1.
export function gainCurve(x, g = WARP_GAMMA) {
  x = Math.max(0, Math.min(1, x));
  return x < 0.5 ? 0.5 * Math.pow(2 * x, g) : 1 - 0.5 * Math.pow(2 * (1 - x), g);
}

// Per-vertex warp factor. eNorm: exposure normalized 0..1; influence: 0..1
// radius falloff (0 → factor 1 exactly, i.e. no distortion claim).
export function warpFactor(eNorm, influence) {
  const wf = WARP_MIN + (WARP_MAX - WARP_MIN) * gainCurve(eNorm);
  return 1 + (wf - 1) * Math.max(0, Math.min(1, influence));
}

// The eNorm at which warpFactor === 1 exactly (inverse of the gain curve at
// the 1.0 crossing) — used by the synthetic tests as the neutral value.
export function neutralENorm() {
  const y = (1 - WARP_MIN) / (WARP_MAX - WARP_MIN);
  return y < 0.5
    ? Math.pow(2 * y, 1 / WARP_GAMMA) / 2
    : 1 - Math.pow(2 * (1 - y), 1 / WARP_GAMMA) / 2;
}

// Regular rows×cols grid over a bounding box. Row index runs along z.
export function buildGrid(minX, minZ, maxX, maxZ, cols, rows) {
  const truePos = new Float64Array(rows * cols * 2);
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const i = r * cols + c;
      truePos[2 * i] = minX + (maxX - minX) * (c / (cols - 1));
      truePos[2 * i + 1] = minZ + (maxZ - minZ) * (r / (rows - 1));
    }
  }
  return { rows, cols, truePos, minX, minZ, maxX, maxZ };
}

// Relax the grid. wf: Float64Array(rows*cols) per-vertex warp factor.
// anchor (optional): Float64Array per-vertex pull-to-true weight per
// iteration — use a small base value for warped vertices and a stronger one
// for zero-influence vertices so unmeasured geometry stays true.
export function relaxMesh(grid, wf, opts = {}) {
  const { rows, cols, truePos: p0 } = grid;
  const iterations = opts.iterations ?? 450;
  const k = opts.stiffness ?? 0.3;
  const regBase = opts.regularization ?? 0.006;   // was 0.012 — the wider warp range needs more freedom
  const tol = opts.tolerance ?? 1e-3;
  const anchor = opts.anchor ?? null;
  const N = rows * cols;
  const pos = Float64Array.from(p0);

  // Axial springs (grid edges) plus diagonal springs per cell: the diagonals
  // give the sheet shear stiffness, without which a locally-expanding region
  // buckles into wrinkles instead of expanding cleanly.
  const edges = [];
  const idx = (r, c) => r * cols + c;
  const mk = (a, b, w) => {
    const d = Math.hypot(p0[2 * b] - p0[2 * a], p0[2 * b + 1] - p0[2 * a + 1]);
    return [a, b, d * (wf[a] + wf[b]) / 2, w];
  };
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      if (c + 1 < cols) edges.push(mk(idx(r, c), idx(r, c + 1), 1.0));
      if (r + 1 < rows) edges.push(mk(idx(r, c), idx(r + 1, c), 1.0));
      if (c + 1 < cols && r + 1 < rows) {
        edges.push(mk(idx(r, c), idx(r + 1, c + 1), 0.75));
        edges.push(mk(idx(r, c + 1), idx(r + 1, c), 0.75));
      }
    }
  }

  // Jacobi-style accumulation: every edge's correction is computed against
  // the same snapshot and applied at once (degree-averaged), so the result
  // is independent of edge ordering — no Gauss-Seidel sweep bias, which
  // otherwise shows up as visible asymmetry at large warp factors.
  const accX = new Float64Array(N), accZ = new Float64Array(N);
  const deg = new Float64Array(N);
  for (const [a, b, , w] of edges) { deg[a] += w; deg[b] += w; }
  const omega = opts.omega ?? 0.8;   // under-relaxation for Jacobi stability

  let maxDisp = Infinity, iter = 0;
  for (; iter < iterations && maxDisp > tol; iter++) {
    accX.fill(0); accZ.fill(0);
    for (const [a, b, target, w] of edges) {
      const dx = pos[2 * b] - pos[2 * a], dz = pos[2 * b + 1] - pos[2 * a + 1];
      const d = Math.hypot(dx, dz) || 1e-9;
      const f = ((d - target) / d) * 0.5 * k * w;
      accX[a] += dx * f; accZ[a] += dz * f;
      accX[b] -= dx * f; accZ[b] -= dz * f;
    }
    maxDisp = 0;
    for (let i = 0; i < N; i++) {
      const scale = omega / Math.max(1, k * deg[i] * 0.5);
      let mx = accX[i] * scale, mz = accZ[i] * scale;
      const w = anchor ? anchor[i] : regBase;
      mx += (p0[2 * i] - pos[2 * i]) * w;
      mz += (p0[2 * i + 1] - pos[2 * i + 1]) * w;
      pos[2 * i] += mx; pos[2 * i + 1] += mz;
      const m = Math.abs(mx) + Math.abs(mz);
      if (m > maxDisp) maxDisp = m;
    }
  }
  return { pos, iterations: iter, maxDisp };
}

// Bilinear map of an arbitrary true-space point through the warped grid.
export function warpPoint(grid, pos, x, z) {
  const { rows, cols, minX, minZ, maxX, maxZ } = grid;
  const fx = (x - minX) / (maxX - minX) * (cols - 1);
  const fz = (z - minZ) / (maxZ - minZ) * (rows - 1);
  const c = Math.max(0, Math.min(cols - 2, Math.floor(fx)));
  const r = Math.max(0, Math.min(rows - 2, Math.floor(fz)));
  const u = Math.max(0, Math.min(1, fx - c));
  const v = Math.max(0, Math.min(1, fz - r));
  const i00 = r * cols + c, i10 = i00 + 1, i01 = i00 + cols, i11 = i01 + 1;
  const X = i => pos[2 * i], Z = i => pos[2 * i + 1];
  return {
    x: (1 - v) * ((1 - u) * X(i00) + u * X(i10)) + v * ((1 - u) * X(i01) + u * X(i11)),
    z: (1 - v) * ((1 - u) * Z(i00) + u * Z(i10)) + v * ((1 - u) * Z(i01) + u * Z(i11)),
  };
}

// Count cells whose signed area flipped sign vs. true geometry (folds).
export function foldedCells(grid, pos) {
  const { rows, cols } = grid;
  const area = (P, i00, i10, i11, i01) => {
    const x = [P[2 * i00], P[2 * i10], P[2 * i11], P[2 * i01]];
    const z = [P[2 * i00 + 1], P[2 * i10 + 1], P[2 * i11 + 1], P[2 * i01 + 1]];
    let a = 0;
    for (let k = 0; k < 4; k++) a += x[k] * z[(k + 1) % 4] - x[(k + 1) % 4] * z[k];
    return a / 2;
  };
  let folded = 0;
  for (let r = 0; r < rows - 1; r++) {
    for (let c = 0; c < cols - 1; c++) {
      const i00 = r * cols + c, i10 = i00 + 1, i01 = i00 + cols, i11 = i01 + 1;
      const a0 = area(grid.truePos, i00, i10, i11, i01);
      const a1 = area(pos, i00, i10, i11, i01);
      if (a0 * a1 <= 0) folded++;
    }
  }
  return folded;
}
