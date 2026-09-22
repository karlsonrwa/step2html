// The pure pieces of the viewer, run by node: no DOM, no WebGL, no browser.
//
// The files are read as they are and evaluated together, the way page.py
// concatenates them, and the functions are pulled out by name. Anything
// that touches the document stays out - boot.js, gl.js, measure.js - and is
// exercised by opening a real page instead (docs/viewer-checklist.md).
//
// What the fixtures here are FOR, since a mutation audit found each one by
// its absence (2026-09-21): every count in the payload is non-zero and no
// two are alike, so an array read at another's offset or stride shows;
// every camera that is measured has a rotation that is not the identity and
// a pivot that is not the origin, or a transposed matrix and a flipped sign
// come back identical; the picked mesh has three triangles at two depths,
// or "the nearest wins" and "the triangle's number" are both 0; and no
// expectation is computed from a constant of the code under test - FOV and
// the fitting margin are written here as numbers.
'use strict';
const fs = require('fs');
const path = require('path');

const dir = path.join(__dirname, '..', 'step2html', 'viewer');
// layout.js is here for oblong() alone: chooseLayout beside it reads the
// window and measures elements, but oblong is arithmetic over two numbers
// and comes out by name like the rest. Nothing in the file touches the
// document until it is called.
//
// overlays.js and measure.js are here for placeMarker and rimPath, which
// take what they work on by argument and are arithmetic: placeMarker writes
// two strings into whatever object it is handed, and rimPath walks a circle
// through a project() given to it. What is left in those two files - the
// element walks of paintAxes and paintMeasure - needs a document and is
// checked in tests/test_browser.py, on the real page.
const src = ['payload.js', 'mat.js', 'camera.js', 'pick.js', 'overlays.js',
             'measure.js', 'hash.js', 'layout.js']
  .map(f => fs.readFileSync(path.join(dir, f), 'utf8')).join('\n');
// globalThis stands in for window: node has DecompressionStream, atob, Blob
// and MessageChannel of its own since 18, which is what inflate needs.
const V = new Function('window', src + '\nreturn {crc32, crcRun, inflate, parsePayload, mul, rotX, rotY, '
  + 'orthonormalise, basis, FOV, fitDist, VIEWS, homeCam, projection, modelView, '
  + 'setDist, setPivot, toModel, toScreen, pxSize, pick, faceOfTriangle, snapAt, '
  + 'SNAP_PX, encodeView, decodeView, oblong, placeMarker, rimPath};')(globalThis);

let failures = 0;
function check(ok, what, detail) {
  console.log(`  ${ok ? 'pass' : 'FAIL'}  ${what}` + (detail ? `   ${detail}` : ''));
  if (!ok) failures++;
}
const near = (a, b, eps = 1e-4) => Math.abs(a - b) <= eps;
const I = new Float32Array([1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1]);
// A 3-vector through the upper-left 3x3 of a column-major matrix.
const apply = (m, v) => [m[0]*v[0] + m[4]*v[1] + m[8]*v[2],
                         m[1]*v[0] + m[5]*v[1] + m[9]*v[2],
                         m[2]*v[0] + m[6]*v[1] + m[10]*v[2]];

// ---- payload ------------------------------------------------------------ #
check(V.crc32(new TextEncoder().encode('123456789')) === 0xCBF43926,
      'crc32 gives the standard check value for 123456789');
{
  // A payload built by hand, version 4. Every count is non-zero and no two
  // counts are equal: with nv=1 and everything else 0 the whole tail of the
  // reader - the triangles, the edges, the face table - was never read at
  // all, and its offsets and strides could be anything.
  const nv = 3, ni = 6, nev = 2, nei = 4, nfa = 2, ncr = 1;
  const body = new ArrayBuffer(48 + nv*12 + nv*3 + nv*3 + ni*4
                               + nev*12 + nei*4 + nfa*4 + ncr*28);
  const dv = new DataView(body);
  [0x53,0x33,0x44,0x48].forEach((c, i) => dv.setUint8(i, c));    // S3DH
  dv.setUint32(4, 4, true);
  [nv, ni, nev, nei, nfa, ncr].forEach((n, i) => dv.setUint32(8 + i*4, n, true));
  dv.setFloat32(32, 7.5, true);
  dv.setFloat32(36, 1, true); dv.setFloat32(40, 2, true); dv.setFloat32(44, 3, true);
  let o = 48;
  const f32 = a => a.forEach(v => { dv.setFloat32(o, v, true); o += 4; });
  const u8  = a => a.forEach(v => { dv.setUint8(o, v); o += 1; });
  const u32 = a => a.forEach(v => { dv.setUint32(o, v, true); o += 4; });
  f32([0.5, -0.5, 0.25,  1, 2, 3,  4, 5, 6]);                    // pos
  u8([128, 255, 1,  2, 3, 4,  5, 6, 7]);                         // nrmB
  u8([10, 20, 30,  40, 50, 60,  70, 80, 90]);                    // colB
  u32([0, 1, 2,  2, 1, 0]);                                      // idx
  f32([9, 8, 7,  6, 5, 4]);                                      // epos
  u32([1, 0, 0, 1]);                                             // eidx
  u32([0, 1]);                                                   // faceAt
  f32([1, 2, 3,  0, 0, 1,  2.5]);                                // cir
  const mesh = V.parsePayload(new Uint8Array(body));
  check(mesh.nv === 3 && mesh.ni === 6 && mesh.nev === 2 && mesh.nei === 4
        && mesh.nfa === 2 && mesh.ncr === 1 && near(mesh.span, 7.5)
        && mesh.half.join() === '1,2,3',
        'parsePayload reads the header',
        JSON.stringify([mesh.nv, mesh.ni, mesh.nev, mesh.nei, mesh.nfa, mesh.ncr,
                        mesh.span, mesh.half]));
  check(near(mesh.pos[0], 0.5) && near(mesh.pos[1], -0.5) && near(mesh.pos[8], 6)
        && mesh.nrmB.join() === '128,255,1,2,3,4,5,6,7'
        && mesh.colB.join() === '10,20,30,40,50,60,70,80,90',
        'and the vertices, the normals and the colours are where the header says');
  // Everything AFTER the per-vertex arrays. One wrong stride shifts all of
  // these at once, so they are read back whole rather than sampled.
  check(mesh.idx.join() === '0,1,2,2,1,0' && mesh.epos.join() === '9,8,7,6,5,4'
        && mesh.eidx.join() === '1,0,0,1' && mesh.faceAt.join() === '0,1'
        && near(mesh.cir[0], 1) && near(mesh.cir[6], 2.5),
        'and so are the triangles, the edges, the face starts and the circles',
        JSON.stringify([[...mesh.idx], [...mesh.epos], [...mesh.eidx],
                        [...mesh.faceAt], [...mesh.cir]]));
  // The first eight bytes, which nothing used to look at: every count is
  // read from a fixed offset, so another file's bytes came out as enormous
  // array lengths and the page called a whole file damaged - or drew
  // nothing at all and said nothing.
  const bytes = new Uint8Array(body);
  const refuse = edit => {
    const copy = bytes.slice();
    if (edit) edit(new DataView(copy.buffer));
    try { V.parsePayload(copy); return 'parsed'; }
    catch (e) { return e && e.kind ? e.kind + ':' + e.got : String(e); }
  };
  check(refuse(dv => dv.setUint8(1, 0x34)) === 'magic:S4DH',
        'a payload that is not S3DH is refused by its magic, and says what it found',
        refuse(dv => dv.setUint8(1, 0x34)));
  check(refuse(dv => dv.setUint32(4, 5, true)) === 'version:5',
        'and one written in a format this page does not read, by its version',
        refuse(dv => dv.setUint32(4, 5, true)));
  let short = 'parsed';
  try { V.parsePayload(bytes.slice(0, 20)); }
  catch (e) { short = e && e.kind ? e.kind + ':' + e.got : String(e); }
  check(short === 'magic:too short',
        'and bytes too few to hold a header are refused before they are read',
        short);
  // And the payload it WAS written for still goes through, which is the
  // half of this that a check written only for the refusals would lose.
  const again = V.parsePayload(bytes);
  check(again.nv === 3 && again.ncr === 1 && near(again.span, 7.5),
        'while the payload of this page\'s own version parses as it did',
        JSON.stringify([again.nv, again.ncr, again.span]));
}

// ---- mat ---------------------------------------------------------------- #
check(Array.from(V.mul(I, I)).join() === Array.from(I).join(), 'the identity times itself is itself');
{
  // A turn of a quarter circle, not of nothing: rotX(0) is the identity
  // whichever way rotX turns, so the sign of the sine had no check at all.
  const q = Math.PI / 2;
  const rxY = apply(V.rotX(q), [0, 1, 0]), ryX = apply(V.rotY(q), [1, 0, 0]);
  check(near(rxY[0], 0) && near(rxY[1], 0) && near(rxY[2], 1)
        && near(ryX[0], 0) && near(ryX[1], 0) && near(ryX[2], -1),
        'a quarter turn about X takes +Y to +Z, and one about Y takes +X to -Z',
        JSON.stringify([rxY.map(v => +v.toFixed(3)), ryX.map(v => +v.toFixed(3))]));
  check(Array.from(V.rotX(0)).join() === Array.from(I).join()
        && Array.from(V.rotY(0)).join() === Array.from(I).join(),
        'and a turn of nothing is the identity');
}
{
  // SHEARED, and not merely scaled. A uniform scale leaves the columns
  // perpendicular already, so the Gram-Schmidt step this function exists for
  // had nothing to do and could be cut without a check noticing.
  const m = V.mul(V.rotX(0.7), V.rotY(-1.1));
  for (let i = 0; i < 16; i++) m[i] *= 1.37;               // scaled
  for (let i = 0; i < 3; i++) m[4 + i] += 0.21 * m[i];     // and sheared
  const r = V.orthonormalise(m);
  const col = j => [r[j*4], r[j*4+1], r[j*4+2]];
  const dot = (a, b) => a[0]*b[0] + a[1]*b[1] + a[2]*b[2];
  const ok = [0, 1, 2].every(j => near(dot(col(j), col(j)), 1, 1e-5))
          && near(dot(col(0), col(1)), 0, 1e-5) && near(dot(col(1), col(2)), 0, 1e-5)
          && near(dot(col(0), col(2)), 0, 1e-5);
  check(ok, 'orthonormalise gives back unit, perpendicular columns');
  // And a RIGHT-handed set. Three perpendicular unit columns with the last
  // one turned round are still perpendicular and still unit, and the model
  // would come back mirrored from every drag.
  const [x, y, z] = [col(0), col(1), col(2)];
  const det = x[0]*(y[1]*z[2] - y[2]*z[1]) - x[1]*(y[0]*z[2] - y[2]*z[0])
            + x[2]*(y[0]*z[1] - y[1]*z[0]);
  check(near(det, 1, 1e-5), 'and a right-handed set: the determinant is +1, not -1',
        det.toFixed(6));
}
{
  const top = V.basis([0,0,1], [0,1,0]);
  check(near(top[2], 0) && near(top[6], 0) && near(top[10], 1),
        'from the top, model Z is the view Z');
  const front = V.basis([0,-1,0], [0,0,1]);
  check(near(front[1], 0) && near(front[5], 0) && near(front[9], 1),
        'from the front, model Z is up on screen');
}

// ---- camera ------------------------------------------------------------- #
// Thirty degrees, written down. Every expectation below used to be computed
// from V.FOV, which meant doubling it moved the check with the code.
check(near(V.FOV, Math.PI / 6, 1e-12), 'the vertical field of view is thirty degrees',
      `${(V.FOV * 180 / Math.PI).toFixed(4)} deg`);
check(V.VIEWS.length === 8, 'there are eight named views');
{
  // The direction each named view looks from, as the third row of its basis.
  // Only the LENGTH of the list was checked before, so two entries could be
  // the same view and the menu would quietly have seven.
  const k = 0.5773503;                        // 1/sqrt(3): an isometric arm
  const want = [[0,0,1], [0,0,-1], [0,-1,0], [0,1,0], [-1,0,0], [1,0,0],
                [k,-k,k], [k,-k,-k]];
  const got = V.VIEWS.map(m => [m[2], m[6], m[10]]);
  check(want.every((w, i) => w.every((v, j) => near(v, got[i][j], 1e-5))),
        'and each looks from the direction its place in the menu names',
        JSON.stringify(got.map(g => g.map(v => +v.toFixed(3)))));
}
{
  const t = Math.tan(V.FOV / 2);
  const d = V.fitDist(I, 1, [1, 1, 1]);
  // The NUMBER, not the formula. tan(15 deg) is 0.2679492, so the corners of
  // a unit cube ask for (1/0.2679492 + 1) * 1.04 = 4.92133.
  check(near(d, 4.92133, 1e-4), 'a unit cube fits at the distance the corners ask for',
        d.toFixed(5));
  // A cube is bound by the height of the frame whatever its width; a WIDE
  // model is bound by the width, and gains from a wider frame.
  check(near(V.fitDist(I, 2, [1, 1, 1]), d, 1e-3), 'a cube is bound by the height, not the width');
  check(V.fitDist(I, 2, [4, 1, 1]) < V.fitDist(I, 1, [4, 1, 1]),
        'a wide model needs less distance in a wider frame');
  const board = [80, 40, 1];
  const cam = V.homeCam(800, 600, board);
  check(cam.dist > 0 && near(cam.oh, cam.dist * t) && cam.pivot.join() === '0,0,0',
        'the home camera is fitted, with oh in step with the distance');
  // The floor under the aspect, pinned from both sides. Nothing measured the
  // home distance itself, so the floor could be moved from 0.2 to 5 - which
  // would open every ordinary window far too close - without a word.
  check(V.homeCam(300, 600, board).dist > V.homeCam(800, 600, board).dist,
        'a narrow canvas is fitted further back: an aspect of 0.5 is not clamped away',
        `${V.homeCam(300, 600, board).dist.toFixed(1)} vs ${V.homeCam(800, 600, board).dist.toFixed(1)}`);
  check(near(V.homeCam(60, 600, board).dist, V.homeCam(120, 600, board).dist, 1e-3),
        'and a sliver of a canvas is clamped, so the camera cannot run away',
        `${V.homeCam(60, 600, board).dist.toFixed(1)} vs ${V.homeCam(120, 600, board).dist.toFixed(1)}`);
  const before = cam.oh / cam.dist;
  V.setDist(cam, 100, cam.dist * 2);
  check(near(cam.oh / cam.dist, before, 1e-6), 'zoom moves oh and dist together');
  V.setDist(cam, 100, 1e-9);
  check(near(cam.dist, 100 * 0.05), 'and the distance is clamped to a twentieth of the span');
  V.setDist(cam, 100, 1e9);
  check(near(cam.dist, 100 * 20), 'and to twenty times it on the way out', cam.dist.toFixed(1));
}
{
  const cam = {pivot: [0,0,0], rot: new Float32Array(I), dist: 50, oh: 50 * Math.tan(V.FOV/2), px: 0, py: 0};
  const MV = V.modelView(cam), P = V.projection(cam, true, 1, 10);
  const c = V.toScreen(MV, P, 100, 100, [0, 0, 0]);
  check(c && near(c[0], 50) && near(c[1], 50), 'the pivot projects to the middle of the canvas',
        JSON.stringify(c));
  const right = V.toScreen(MV, P, 100, 100, [cam.oh, 0, 0]);
  check(right && near(right[0], 100) && near(right[1], 50), 'and oh is half the height of the view');
  // UPWARDS as well as sideways. Screen y runs downwards, so a point oh
  // ABOVE the pivot belongs at the top edge - and until this was here
  // nothing read the vertical scale of the projection or the flip with it.
  const up = V.toScreen(MV, P, 100, 100, [0, cam.oh, 0]);
  check(up && near(up[0], 50) && near(up[1], 0),
        'a point oh above the pivot is at the TOP of the canvas, not the bottom',
        JSON.stringify(up));
  // The depth range, which toScreen cannot show because it answers x and y
  // only: generous on purpose, span*4 either side of the pivot, so a pivot
  // on the near face still leaves the far side inside. With dist 50 and span
  // 10 that is zn=10, zf=90, hence -2/80 and -100/80.
  check(near(P[10], -0.025, 1e-6) && near(P[14], -1.25, 1e-6),
        'the orthographic depth range is span*4 either side of the pivot',
        `${P[10]} / ${P[14]}`);
  // The two projections show the SAME size at the depth of the pivot: that
  // is what oh is, and why flipping between them does not jump. Nothing
  // measured the perspective scale before, only its w row.
  const pp = V.projection(cam, false, 1, 10);
  const pright = V.toScreen(MV, pp, 100, 100, [cam.oh, 0, 0]);
  check(pright && near(pright[0], 100, 1e-3) && near(pright[1], 50, 1e-3),
        'and the perspective view is the same size there, so flipping does not jump',
        JSON.stringify(pright));
  // Its clipping planes: span*1.5 either side of the pivot. dist 50, span 10
  // gives zn=35 and zf=65, hence (65+35)/(35-65) and 2*65*35/(35-65).
  check(near(pp[10], -3.33333, 1e-4) && near(pp[14], -151.6667, 1e-3),
        'the perspective clipping planes are span*1.5 either side of the pivot',
        `${pp[10].toFixed(5)} / ${pp[14].toFixed(4)}`);
  // And the floor under the near plane, which a camera closer to the pivot
  // than the model is deep runs into: dist 5 with span 10 asks for -10, and
  // a near plane at or below zero is a blank frame. Floored at span*.005 it
  // is 0.05, with zf=20, hence -20.05/19.95 and -2/19.95.
  const close = {pivot: [0,0,0], rot: new Float32Array(I), dist: 5,
                 oh: 5 * Math.tan(V.FOV/2), px: 0, py: 0};
  const cp = V.projection(close, false, 1, 10);
  check(near(cp[10], -1.005013, 1e-5) && near(cp[14], -0.1002506, 1e-6),
        'and the near one has a floor, so a close camera does not draw a blank frame',
        `${cp[10].toFixed(6)} / ${cp[14].toFixed(7)}`);
  // pxSize in perspective, which is its own branch and was never run: at the
  // pivot 2*tan(15 deg)*50/200 = 0.1339746, and twice that at twice the
  // depth, because a pixel covers more of the model further away.
  check(near(V.pxSize(cam, MV, false, 200, [0,0,0]), 0.1339746, 1e-6)
        && near(V.pxSize(cam, MV, false, 200, [0,0,-50]), 0.2679492, 1e-6),
        'pxSize in perspective follows the depth of the point',
        `${V.pxSize(cam, MV, false, 200, [0,0,0])} / ${V.pxSize(cam, MV, false, 200, [0,0,-50])}`);
  const back = V.toModel(cam, MV, [0, 0, -cam.dist], false);
  check(near(back[0], 0) && near(back[1], 0) && near(back[2], 0), 'toModel undoes the model view');
  V.setPivot(cam, MV, [3, 4, 0]);
  check(cam.pivot.join() === '3,4,0' && near(cam.px, 3) && near(cam.py, 4) && near(cam.dist, 50),
        'moving the pivot keeps the picture where it was');
  const persp = V.projection(cam, false, 1.5, 10);
  check(persp[11] === -1 && P[15] === 1, 'perspective and orthographic are told apart by the w row');
}
{
  // Behind the camera. The lens sits fifty model units in front of the pivot
  // looking towards it, so z = +200 is far behind it; the guard that refuses
  // such a point had never been seen to fire, and an overlay placed from it
  // would appear mirrored in front of the model.
  const cam = {pivot: [0,0,0], rot: new Float32Array(I), dist: 50, oh: 50 * Math.tan(V.FOV/2), px: 0, py: 0};
  const MV = V.modelView(cam), P = V.projection(cam, false, 1, 10);
  const behind = V.toScreen(MV, P, 100, 100, [0, 0, 200]);
  check(behind === null, 'a point behind the camera is refused, not projected in front',
        JSON.stringify(behind));
}
{
  // A camera whose pivot is NOT the origin and whose rotation is NOT the
  // identity. Every matrix measured above is built from [0,0,0] and I, which
  // hides the sign of the pivot translation and makes a rotation and its
  // transpose the same three numbers.
  const pivot = [7, -3, 2];
  const cam = {pivot, rot: V.rotY(0.6), dist: 50, oh: 50 * Math.tan(V.FOV/2), px: 0, py: 0};
  const MV = V.modelView(cam), P = V.projection(cam, true, 1, 100);
  const at = V.toScreen(MV, P, 100, 100, pivot);
  check(at && near(at[0], 50) && near(at[1], 50),
        'the centre of the turn is in the middle of the canvas wherever it sits in the model',
        JSON.stringify(at));
  // One unit to the right ON SCREEN, put back into model coordinates: the
  // first ROW of the rotation, [cos .6, 0, sin .6] = [0.825336, 0, 0.564642],
  // and not the transpose's [cos .6, 0, -sin .6].
  const outward = V.toModel(cam, MV, [1, 0, -cam.dist], false).map((v, i) => v - pivot[i]);
  check(near(outward[0], 0.825336, 1e-5) && near(outward[1], 0, 1e-5)
        && near(outward[2], 0.564642, 1e-5),
        'and a step right on screen is the first row of the rotation, not its transpose',
        JSON.stringify(outward.map(v => +v.toFixed(6))));
}

// ---- pick --------------------------------------------------------------- #
{
  // THREE triangles under the same point: a far one, a near one, a far one
  // again. With a single triangle "the nearest wins" and "the triangle is
  // named by its number" are both satisfied by 0 and neither is proved. The
  // near one stands at z = 60 while the pivot is at z = 0 - which is what a
  // click on a near surface does, and what the ray's origin offset is for.
  const mesh = {pos: new Float32Array([0,0,0, 10,0,0, 0,10,0,
                                       0,0,60, 10,0,60, 0,10,60,
                                       0,0,0, 10,0,0, 0,10,0]),
                idx: new Uint32Array([0,1,2, 3,4,5, 6,7,8]), ni: 9};
  const span = 60;
  const cam = {pivot: [0,0,0], rot: new Float32Array(I), dist: 50, oh: 50 * Math.tan(V.FOV/2), px: 0, py: 0};
  const MV = V.modelView(cam);
  const rect = {left: 0, top: 0, width: 100, height: 100};
  const nx = 2 / cam.oh, ny = 2 / cam.oh;                 // model (2, 2) in ortho
  const got = V.pick(mesh, cam, MV, true, span, rect, (nx + 1) / 2 * 100, (1 - ny) / 2 * 100);
  check(got && near(got.hit[0], 2, 1e-3) && near(got.hit[1], 2, 1e-3)
        && near(got.hit[2], 60, 1e-3) && got.tri === 1,
        'an orthographic ray takes the NEAREST triangle, and names it by its number',
        got ? JSON.stringify([got.hit.map(v => +v.toFixed(3)), got.tri]) : 'miss');
  check(V.pick(mesh, cam, MV, true, span, rect, 5, 95) === null, 'and misses beside it');
  // A canvas that is neither square nor at the corner of the window: the
  // aspect stretches the ray sideways and rect.left/top take the cursor out
  // of page coordinates. Both were invisible against 100 by 100 at (0, 0).
  const wide = {left: 30, top: 10, width: 200, height: 100};
  const wx = 1 / cam.oh, wy = 2 / cam.oh;                 // a = 2, so x is 2 model units
  const w = V.pick(mesh, cam, MV, true, span, wide,
                   wide.left + (wx + 1) / 2 * 200, wide.top + (1 - wy) / 2 * 100);
  check(w && near(w.hit[0], 2, 1e-3) && near(w.hit[1], 2, 1e-3) && near(w.hit[2], 60, 1e-3),
        'the ray answers the aspect of the canvas and where it sits on the page',
        w ? JSON.stringify(w.hit.map(v => +v.toFixed(3))) : 'miss');
  const pgot = V.pick(mesh, cam, MV, false, span, rect, 50, 50);
  check(pgot && near(pgot.hit[0], 0, 1e-3) && near(pgot.hit[1], 0, 1e-3)
        && near(pgot.hit[2], 0, 1e-3) && pgot.tri === 0,
        'a perspective ray through the centre hits the origin',
        pgot ? JSON.stringify([pgot.hit.map(v => +v.toFixed(3)), pgot.tri]) : 'miss');
  check(V.faceOfTriangle(new Uint32Array([0, 5, 9]), 3, 6) === 1
        && V.faceOfTriangle(new Uint32Array([0, 5, 9]), 3, 12) === 2
        && V.faceOfTriangle(new Uint32Array([0, 5, 9]), 3, 0) === 0
        && V.faceOfTriangle(new Uint32Array([0, 5, 9]), 3, -1) === -1,
        'faceOfTriangle finds the face a triangle starts in');
  // The FIRST triangle of a face, which is where an off-by-one lives: a
  // search written with < instead of <= hands it to the face before, and
  // every other triangle still lands right.
  check(V.faceOfTriangle(new Uint32Array([0, 5, 9]), 3, 5) === 1
        && V.faceOfTriangle(new Uint32Array([0, 5, 9]), 3, 9) === 2
        && V.faceOfTriangle(new Uint32Array([0, 5, 9]), 0, 4) === -1,
        'and a triangle exactly at a face start belongs to THAT face, not the one before');
  const cir = new Float32Array([0,0,0, 0,0,1, 5]);
  const s = V.snapAt(cir, 1, [5.1, 0, 0], 0.5);
  check(s && s.p.join() === '0,0,0' && s.r === 5, 'a point near the rim snaps to the centre');
  check(V.snapAt(cir, 1, [2, 0, 0], 0.5) === null, 'a point off the rim does not');
  check(V.snapAt(cir, 1, [5, 0, 1], 0.5) === null, 'nor one out of the plane of the circle');
  check(V.snapAt(cir, 0, [5, 0, 0], 0.5) === null && V.snapAt(cir, 1, null, 0.5) === null,
        'and nothing snaps to nothing');
  // Two rims within reach, the nearer one first and then second: with one
  // circle in the fixture the running best was never compared with anything
  // and a click could have taken whichever hole came last in the file.
  const first = V.snapAt(new Float32Array([0,0,0, 0,0,1, 6.15,  8,0,0, 0,0,1, 2]),
                         2, [6.1, 0, 0], 0.5);
  const second = V.snapAt(new Float32Array([0,0,0, 0,0,1, 6.3,   8,0,0, 0,0,1, 2]),
                          2, [6.1, 0, 0], 0.5);
  check(first && near(first.r, 6.15, 1e-5) && second && near(second.r, 2, 1e-5),
        'of two rims within reach the NEARER is caught, whichever comes first',
        JSON.stringify([first && +first.r.toFixed(3), second && +second.r.toFixed(3)]));
  // A pin, not a measurement: the reach is SNAP_PX pixels turned into model
  // units at the depth of the point (boot.js), and nothing outside a browser
  // can see it. Here so that changing it has to be meant.
  check(V.SNAP_PX === 14, 'the snap reaches fourteen pixels', String(V.SNAP_PX));
  check(near(V.pxSize(cam, MV, true, 200, [0,0,0]), 2 * cam.oh / 200), 'pxSize in ortho is oh per half height');
}

// ---- overlays ------------------------------------------------------------ #
{
  // The marker over the canvas is placed by the SAME mapping the rest of
  // the page projects with. It used to carry its own copy of it - the
  // perspective divide and the pixel mapping written out again from MVP -
  // and two copies of one rule drift the day a projection changes.
  // Measured off centre and off axis on purpose: at the middle of the
  // canvas, and with a pivot at the origin, every wrong mapping agrees with
  // the right one.
  const cam = {pivot: [7, -3, 2], rot: V.rotY(0.6), dist: 50,
               oh: 50 * Math.tan(V.FOV / 2), px: 4, py: -6};
  const MV = V.modelView(cam), P = V.projection(cam, false, 1.7, 10);
  const p = [9, -1, 3];
  const want = V.toScreen(MV, P, 800, 600, p);
  const marker = {style: {left: 'x', top: 'y'}};
  V.placeMarker(marker, MV, P, p, 800, 600);
  check(want && marker.style.left === want[0] + 'px'
        && marker.style.top === want[1] + 'px'
        && Math.abs(want[0] - 400) > 20 && Math.abs(want[1] - 300) > 20,
        'placeMarker puts the marker exactly where toScreen puts the point',
        `${marker.style.left},${marker.style.top} for ${want && want.map(v => +v.toFixed(2))}`);
  // Behind the camera there is no pixel to put it on, and the last one it
  // had is better than one mirrored in front of the model.
  const held = {style: {left: '12px', top: '34px'}};
  V.placeMarker(held, MV, P, [7, -3, 400], 800, 600);
  check(held.style.left === '12px' && held.style.top === '34px',
        'and leaves it where it was for a point behind the camera',
        `${held.style.left},${held.style.top}`);
}

// ---- measure: the caught rim as a screen path ---------------------------- #
{
  const cam = {pivot: [0, 0, 0], rot: new Float32Array(I), dist: 50,
               oh: 50 * Math.tan(V.FOV / 2), px: 0, py: 0};
  const MV = V.modelView(cam), P = V.projection(cam, false, 1, 10);
  const project = q => V.toScreen(MV, P, 400, 400, q);
  const circle = {p: [0, 0, 0], n: [0, 0, 1], r: 5};
  const path = V.rimPath(circle, project);
  const pts = path.split(' ');
  // Forty-eight steps round the circle, so the first and the last point are
  // the same place and the ring closes.
  check(pts.length === 49 && pts[0] === pts[48],
        'a rim comes back as 48 samples round the circle, closed',
        `${pts.length} points, first ${pts[0]}, last ${pts[48]}`);
  const r0 = pts[0].split(',').map(Number);
  const mid = pts[24].split(',').map(Number);
  // Seen face on, so it projects to a circle about the projection of its
  // own centre: opposite samples straddle that centre, and every sample is
  // the same distance from it.
  const rad = pts.slice(0, 48).map(s => {
    const [x, y] = s.split(',').map(Number);
    return Math.hypot(x - 200, y - 200);
  });
  const spread = Math.max(...rad) - Math.min(...rad);
  check(Math.abs((r0[0] + mid[0]) / 2 - 200) < .01
        && Math.abs((r0[1] + mid[1]) / 2 - 200) < .01
        && spread < .12 && rad[0] > 50,     // written to a tenth of a pixel
        'and it is the circle itself, about the centre it was taken from',
        `${rad[0].toFixed(1)} px out, spread ${spread.toFixed(3)} px`);
  // A rim that runs past the lens. One sample behind the camera and the
  // path is not a ring any more but a line across the view, so there is
  // nothing honest to draw - hence '' rather than half a circle.
  const near_ = {pivot: [0, 0, 0], rot: new Float32Array(I), dist: 5,
                 oh: 5 * Math.tan(V.FOV / 2), px: 0, py: 0};
  const nMV = V.modelView(near_), nP = V.projection(near_, false, 1, 10);
  const huge = {p: [0, 0, 0], n: [0, 1, 0], r: 40};
  check(V.rimPath(huge, q => V.toScreen(nMV, nP, 400, 400, q)) === '',
        'a rim with a point behind the camera is not drawn at all');
}

// ---- hash --------------------------------------------------------------- #
{
  // Values that need all six digits, and a rotation that is NOT symmetric.
  // With the identity a transposed rotation comes back identical, and with
  // round numbers three significant digits would have done. 120000 stays:
  // it is the number the trailing-zero bug of 0.9.x turned into 12.
  const rot = V.rotY(0.6);
  const cam = {rot, dist: 120000, oh: 1234.56, px: 0.123456, py: -0.25,
               pivot: [1e6, 3.14159, 4]};
  const h = V.encodeView(cam);
  const back = V.decodeView(h);
  check(back && back.dist === 120000 && back.oh === 1234.56 && back.pivot[0] === 1e6
        && back.pivot[1] === 3.14159 && back.px === 0.123456 && back.py === -0.25,
        'the view survives the address to six digits, 120000 and a million included', h);
  check(back && [0,1,2,4,5,6,8,9,10].every(i => near(back.rot[i], rot[i], 1e-5)),
        'and so does the rotation, the way round it was',
        back ? Array.from(back.rot).map(v => +v.toFixed(4)).join() : 'null');
  check(V.decodeView('#v=1,2,3') === null && V.decodeView('') === null
        && V.decodeView('#v=a,b') === null && V.decodeView(null) === null,
        'anything that is not sixteen numbers is ignored');
  // Sixteen fields that all match the character class and none of which is a
  // number: the only case the NaN guard can answer, and one none of the four
  // above ever reaches - they are turned away by the pattern itself.
  const sixteen = '#v=' + new Array(16).fill('e').join(',');
  check(V.decodeView(sixteen) === null,
        'and sixteen fields that are not numbers are ignored too',
        JSON.stringify(V.decodeView(sixteen)));
}
{
  // An address written out BY HAND, and what each of its sixteen fields
  // must become. Everything above goes through encodeView first, so the two
  // halves could agree on a wrong order - or on a field read twice - and
  // the round trip would still close: it was pivot[2] that had no check at
  // all, because the one above reads back only the first two. Sixteen
  // values, all different, none of them a round number.
  const h = '#v=0.11,0.22,0.33,0.44,0.55,0.66,0.77,0.88,0.99,'
          + '137.25,35.5,-2.5,4.25,10.5,-20.25,30.125';
  const v = V.decodeView(h);
  const rot = v && Array.from(v.rot);
  check(v && v.dist === 137.25 && v.oh === 35.5 && v.px === -2.5
        && v.py === 4.25 && v.pivot.join() === '10.5,-20.25,30.125',
        'a hand-written address decodes field by field into the camera it names',
        v ? JSON.stringify([v.dist, v.oh, v.px, v.py, v.pivot]) : 'null');
  // The nine of the rotation into the upper-left 3x3 of a 4x4, in reading
  // order, with the fourth column and row left as they must be.
  const want = [0.11, 0.22, 0.33, 0, 0.44, 0.55, 0.66, 0, 0.77, 0.88, 0.99, 0,
                0, 0, 0, 1];
  check(rot && want.every((w, i) => near(rot[i], w, 1e-6)),
        'and its nine rotation fields into the matrix, in that order',
        rot ? rot.map(x => +x.toFixed(3)).join() : 'null');
}

// ---- layout ------------------------------------------------------------- #
// How far from square a view is, which is the whole of the decision about
// where the bar goes. The rest of layout.js measures elements and cannot be
// run here; this much can, and had no check at all.
check(near(V.oblong(400, 100), 4) && near(V.oblong(100, 400), 4),
      'a view is as oblong lying down as it is standing up',
      `${V.oblong(400, 100)} / ${V.oblong(100, 400)}`);
check(Number.isFinite(V.oblong(0, 0)) && Number.isFinite(V.oblong(0, 100)),
      'and a window that has not been laid out yet still answers a number',
      `${V.oblong(0, 0)} / ${V.oblong(0, 100)}`);

// ---- inflate: from the page's text to the bytes, with the counter ------- #
// Async, so it runs last and the verdict waits for it.
(async () => {
  const zlib = require('zlib');
  // INCOMPRESSIBLE on purpose. The base64 has to be longer than one 4 MiB
  // slice of the decoding loop or that loop runs once and the counter it
  // feeds is never seen to move: the old body, built from i*7919, deflated
  // 5 MiB down to 45 kB and came to a single slice.
  const body = Buffer.alloc(4 * 1024 * 1024);
  let s = 0x9E3779B9 | 0;
  for (let i = 0; i < body.length; i++) {
    s ^= s << 13; s >>>= 0; s ^= s >>> 17; s ^= s << 5; s >>>= 0; body[i] = s & 255;
  }
  const b64 = zlib.deflateRawSync(body).toString('base64');
  check(b64.length > (1 << 22), 'the test body is longer than one slice of the decoding loop',
        `${b64.length} base64 characters`);
  const seen = [];
  let out = null, why = '';
  try { out = await V.inflate(b64, body.length, (phase, f) => seen.push([phase, f])); }
  catch (e) { why = JSON.stringify(e); }
  check(out && Buffer.compare(Buffer.from(out.bin), body) === 0,
        'inflate gives back the bytes deflate took', why || `${out && out.bin.length} bytes`);
  check(out && out.crc === V.crc32(out.bin) && out.crc === (zlib.crc32 ? zlib.crc32(body) : out.crc),
        'and the CRC it ran alongside is the CRC of the whole');
  const decode = seen.filter(x => x[0] === 'decode').map(x => x[1]);
  const inflate = seen.filter(x => x[0] === 'inflate').map(x => x[1]);
  const up = a => a.every((v, i) => i === 0 || v >= a[i - 1]);
  check(decode.length >= 2 && decode[0] < 1 && decode[decode.length - 1] === 1 && up(decode),
        'the decode counter moves BEFORE the end, only up, and finishes at 1',
        JSON.stringify(decode.map(v => +v.toFixed(4))));
  check(inflate.length >= 2 && inflate[inflate.length - 1] === 1 && up(inflate),
        'and so does the inflate counter', `${inflate.length} steps`);
  check(seen.findIndex(x => x[0] === 'inflate') > seen.map(x => x[0]).lastIndexOf('decode'),
        'decoding is reported before inflating, never after');
  // A page that promises more bytes than arrive - a truncated payload, or a
  // length written wrong. The running fraction never reaches 1, so the last
  // word has to come from the report made after the stream ends, or the
  // counter stops part way and the page looks hung.
  const short = zlib.deflateRawSync(Buffer.alloc(1000, 7)).toString('base64');
  const said = [];
  await V.inflate(short, 4000, (phase, f) => { if (phase === 'inflate') said.push(f); });
  check(said.length >= 1 && said[said.length - 1] === 1,
        'and it reaches 1 even when the page promises more bytes than arrive',
        JSON.stringify(said));
  let kind = null;
  try { await V.inflate('not base64 at all!!', 10, () => {}); } catch (e) { kind = e && e.kind; }
  check(kind === 'unpack', 'text that is not a payload is reported as damage, not as old',
        String(kind));
  console.log(failures ? `${failures} FAILED` : 'all passed');
  process.exit(failures ? 1 : 0);
})();
