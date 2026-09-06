// The pure pieces of the viewer, run by node: no DOM, no WebGL, no browser.
//
// The files are read as they are and evaluated together, the way page.py
// concatenates them, and the functions are pulled out by name. Anything
// that touches the document stays out - boot.js, gl.js, measure.js - and is
// exercised by opening a real page instead (docs/viewer-checklist.md).
'use strict';
const fs = require('fs');
const path = require('path');

const dir = path.join(__dirname, '..', 'step2html', 'viewer');
const src = ['payload.js', 'mat.js', 'camera.js', 'pick.js', 'hash.js']
  .map(f => fs.readFileSync(path.join(dir, f), 'utf8')).join('\n');
// globalThis stands in for window: node has DecompressionStream, atob, Blob
// and MessageChannel of its own since 18, which is what inflate needs.
const V = new Function('window', src + '\nreturn {crc32, crcRun, inflate, parsePayload, mul, rotX, rotY, '
  + 'orthonormalise, basis, FOV, fitDist, VIEWS, homeCam, projection, modelView, '
  + 'setDist, setPivot, toModel, toScreen, pxSize, pick, faceOfTriangle, snapAt, '
  + 'SNAP_PX, encodeView, decodeView};')(globalThis);

let failures = 0;
function check(ok, what, detail) {
  console.log(`  ${ok ? 'pass' : 'FAIL'}  ${what}` + (detail ? `   ${detail}` : ''));
  if (!ok) failures++;
}
const near = (a, b, eps = 1e-4) => Math.abs(a - b) <= eps;
const I = new Float32Array([1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1]);

// ---- payload ------------------------------------------------------------ #
check(V.crc32(new TextEncoder().encode('123456789')) === 0xCBF43926,
      'crc32 gives the standard check value for 123456789');
{
  // A one-vertex, no-triangle payload built by hand, version 4.
  const nv = 1, ni = 0, nev = 0, nei = 0, nfa = 1, ncr = 1;
  const body = new ArrayBuffer(48 + nv*12 + nv*3 + nv*3 + nfa*4 + ncr*28);
  const dv = new DataView(body);
  [0x53,0x33,0x44,0x48].forEach((c, i) => dv.setUint8(i, c));    // S3DH
  dv.setUint32(4, 4, true);
  [nv, ni, nev, nei, nfa, ncr].forEach((n, i) => dv.setUint32(8 + i*4, n, true));
  dv.setFloat32(32, 7.5, true);
  dv.setFloat32(36, 1, true); dv.setFloat32(40, 2, true); dv.setFloat32(44, 3, true);
  let o = 48;
  dv.setFloat32(o, 0.5, true); dv.setFloat32(o+4, -0.5, true); dv.setFloat32(o+8, 0.25, true); o += 12;
  dv.setUint8(o, 128); dv.setUint8(o+1, 255); dv.setUint8(o+2, 1); o += 3;
  dv.setUint8(o, 10); dv.setUint8(o+1, 20); dv.setUint8(o+2, 30); o += 3;
  dv.setUint32(o, 0, true); o += 4;
  [1, 2, 3, 0, 0, 1, 2.5].forEach((f, i) => dv.setFloat32(o + i*4, f, true));
  const mesh = V.parsePayload(new Uint8Array(body));
  check(mesh.nv === 1 && mesh.nfa === 1 && mesh.ncr === 1 && near(mesh.span, 7.5)
        && mesh.half.join() === '1,2,3',
        'parsePayload reads the header', JSON.stringify([mesh.nv, mesh.span, mesh.half]));
  check(near(mesh.pos[0], 0.5) && near(mesh.pos[1], -0.5) && mesh.nrmB[1] === 255
        && mesh.colB[2] === 30 && mesh.faceAt[0] === 0 && near(mesh.cir[6], 2.5),
        'and every array is where the header says');
}

// ---- mat ---------------------------------------------------------------- #
check(Array.from(V.mul(I, I)).join() === Array.from(I).join(), 'the identity times itself is itself');
check(Array.from(V.rotX(0)).join() === Array.from(I).join()
      && Array.from(V.rotY(0)).join() === Array.from(I).join(),
      'a turn of nothing is the identity');
{
  const m = V.mul(V.rotX(0.7), V.rotY(-1.1));
  for (let i = 0; i < 16; i++) m[i] *= 1.37;              // sheared and scaled
  const r = V.orthonormalise(m);
  const col = j => [r[j*4], r[j*4+1], r[j*4+2]];
  const dot = (a, b) => a[0]*b[0] + a[1]*b[1] + a[2]*b[2];
  const ok = [0, 1, 2].every(j => near(dot(col(j), col(j)), 1, 1e-5))
          && near(dot(col(0), col(1)), 0, 1e-5) && near(dot(col(1), col(2)), 0, 1e-5);
  check(ok, 'orthonormalise gives back unit, perpendicular columns');
}
check(V.VIEWS.length === 8, 'there are eight named views');
{
  const top = V.basis([0,0,1], [0,1,0]);
  check(near(top[2], 0) && near(top[6], 0) && near(top[10], 1),
        'from the top, model Z is the view Z');
  const front = V.basis([0,-1,0], [0,0,1]);
  check(near(front[1], 0) && near(front[5], 0) && near(front[9], 1),
        'from the front, model Z is up on screen');
}

// ---- camera ------------------------------------------------------------- #
{
  const t = Math.tan(V.FOV / 2);
  const d = V.fitDist(I, 1, [1, 1, 1]);
  check(near(d, (1 / t + 1) * 1.04, 1e-3), 'a unit cube fits at the distance the corners ask for',
        d.toFixed(4));
  // A cube is bound by the height of the frame whatever its width; a WIDE
  // model is bound by the width, and gains from a wider frame.
  check(near(V.fitDist(I, 2, [1, 1, 1]), d, 1e-3), 'a cube is bound by the height, not the width');
  check(V.fitDist(I, 2, [4, 1, 1]) < V.fitDist(I, 1, [4, 1, 1]),
        'a wide model needs less distance in a wider frame');
  const cam = V.homeCam(800, 600, [80, 40, 1]);
  check(cam.dist > 0 && near(cam.oh, cam.dist * t) && cam.pivot.join() === '0,0,0',
        'the home camera is fitted, with oh in step with the distance');
  const before = cam.oh / cam.dist;
  V.setDist(cam, 100, cam.dist * 2);
  check(near(cam.oh / cam.dist, before, 1e-6), 'zoom moves oh and dist together');
  V.setDist(cam, 100, 1e-9);
  check(near(cam.dist, 100 * 0.05), 'and the distance is clamped to the model');
}
{
  const cam = {pivot: [0,0,0], rot: new Float32Array(I), dist: 50, oh: 50 * Math.tan(V.FOV/2), px: 0, py: 0};
  const MV = V.modelView(cam), P = V.projection(cam, true, 1, 10);
  const c = V.toScreen(MV, P, 100, 100, [0, 0, 0]);
  check(c && near(c[0], 50) && near(c[1], 50), 'the pivot projects to the middle of the canvas',
        JSON.stringify(c));
  const right = V.toScreen(MV, P, 100, 100, [cam.oh, 0, 0]);
  check(right && near(right[0], 100) && near(right[1], 50), 'and oh is half the height of the view');
  const back = V.toModel(cam, MV, [0, 0, -cam.dist], false);
  check(near(back[0], 0) && near(back[1], 0) && near(back[2], 0), 'toModel undoes the model view');
  V.setPivot(cam, MV, [3, 4, 0]);
  check(cam.pivot.join() === '3,4,0' && near(cam.px, 3) && near(cam.py, 4) && near(cam.dist, 50),
        'moving the pivot keeps the picture where it was');
  const persp = V.projection(cam, false, 1.5, 10);
  check(persp[11] === -1 && P[15] === 1, 'perspective and orthographic are told apart by the w row');
}

// ---- pick --------------------------------------------------------------- #
{
  const mesh = {pos: new Float32Array([0,0,0, 10,0,0, 0,10,0]), idx: new Uint32Array([0,1,2]), ni: 3};
  const cam = {pivot: [0,0,0], rot: new Float32Array(I), dist: 50, oh: 50 * Math.tan(V.FOV/2), px: 0, py: 0};
  const MV = V.modelView(cam);
  const rect = {left: 0, top: 0, width: 100, height: 100};
  const nx = 2 / cam.oh, ny = 2 / cam.oh;                 // model (2, 2) in ortho
  const got = V.pick(mesh, cam, MV, true, 10, rect, (nx + 1) / 2 * 100, (1 - ny) / 2 * 100);
  check(got && near(got.hit[0], 2, 1e-3) && near(got.hit[1], 2, 1e-3) && near(got.hit[2], 0, 1e-3)
        && got.tri === 0, 'an orthographic ray hits the triangle where it should',
        got ? JSON.stringify(got.hit.map(v => +v.toFixed(3))) : 'miss');
  check(V.pick(mesh, cam, MV, true, 10, rect, 5, 95) === null, 'and misses beside it');
  const pgot = V.pick(mesh, cam, MV, false, 10, rect, 50, 50);
  check(pgot && near(pgot.hit[0], 0, 1e-3) && near(pgot.hit[1], 0, 1e-3),
        'a perspective ray through the centre hits the origin');
  check(V.faceOfTriangle(new Uint32Array([0, 5, 9]), 3, 6) === 1
        && V.faceOfTriangle(new Uint32Array([0, 5, 9]), 3, 12) === 2
        && V.faceOfTriangle(new Uint32Array([0, 5, 9]), 3, 0) === 0
        && V.faceOfTriangle(new Uint32Array([0, 5, 9]), 3, -1) === -1,
        'faceOfTriangle finds the face a triangle starts in');
  const cir = new Float32Array([0,0,0, 0,0,1, 5]);
  const s = V.snapAt(cir, 1, [5.1, 0, 0], 0.5);
  check(s && s.p.join() === '0,0,0' && s.r === 5, 'a point near the rim snaps to the centre');
  check(V.snapAt(cir, 1, [2, 0, 0], 0.5) === null, 'a point off the rim does not');
  check(V.snapAt(cir, 1, [5, 0, 1], 0.5) === null, 'nor one out of the plane of the circle');
  check(V.snapAt(cir, 0, [5, 0, 0], 0.5) === null && V.snapAt(cir, 1, null, 0.5) === null,
        'and nothing snaps to nothing');
  check(near(V.pxSize(cam, MV, true, 200, [0,0,0]), 2 * cam.oh / 200), 'pxSize in ortho is oh per half height');
}

// ---- hash --------------------------------------------------------------- #
{
  const cam = {rot: new Float32Array(I), dist: 120000, oh: 1200, px: 0.5, py: -0.25, pivot: [1e6, 3, 4]};
  const h = V.encodeView(cam);
  const back = V.decodeView(h);
  check(back && back.dist === 120000 && back.oh === 1200 && back.pivot[0] === 1e6
        && back.px === 0.5 && back.py === -0.25,
        'the view survives the address, 120000 and a million included', h);
  check(Array.from(back.rot).join() === Array.from(I).join(), 'and so does the rotation');
  check(V.decodeView('#v=1,2,3') === null && V.decodeView('') === null
        && V.decodeView('#v=a,b') === null && V.decodeView(null) === null,
        'anything that is not sixteen numbers is ignored');
}

// ---- inflate: from the page's text to the bytes, with the counter ------- #
// Async, so it runs last and the verdict waits for it. The body is longer
// than one slice of the base64 loop and than one chunk of the stream, so
// both counters have to move more than once.
(async () => {
  const zlib = require('zlib');
  const body = Buffer.alloc(5 * 1024 * 1024);
  for (let i = 0; i < body.length; i++) body[i] = (i * 7919 + (i >> 12)) & 255;
  const b64 = zlib.deflateRawSync(body).toString('base64');
  const seen = [];
  let out = null, why = '';
  try { out = await V.inflate(b64, body.length, (phase, f) => seen.push([phase, f])); }
  catch (e) { why = JSON.stringify(e); }
  check(out && Buffer.compare(Buffer.from(out.bin), body) === 0,
        'inflate gives back the bytes deflate took', why || `${out && out.bin.length} bytes`);
  check(out && out.crc === V.crc32(out.bin) && out.crc === (zlib.crc32 ? zlib.crc32(body) : out.crc),
        'and the CRC it ran alongside is the CRC of the whole');
  const decode = seen.filter(s => s[0] === 'decode').map(s => s[1]);
  const inflate = seen.filter(s => s[0] === 'inflate').map(s => s[1]);
  const up = a => a.every((v, i) => i === 0 || v >= a[i - 1]);
  check(decode.length >= 1 && decode[decode.length - 1] === 1 && up(decode),
        'the decode counter only goes up, to 1', JSON.stringify(decode.slice(0, 4)));
  check(inflate.length >= 2 && inflate[inflate.length - 1] === 1 && up(inflate),
        'and so does the inflate counter', `${inflate.length} steps`);
  check(seen.findIndex(s => s[0] === 'inflate') > seen.map(s => s[0]).lastIndexOf('decode'),
        'decoding is reported before inflating, never after');
  let kind = null;
  try { await V.inflate('not base64 at all!!', 10, () => {}); } catch (e) { kind = e && e.kind; }
  check(kind === 'unpack', 'text that is not a payload is reported as damage, not as old',
        String(kind));
  console.log(failures ? `${failures} FAILED` : 'all passed');
  process.exit(failures ? 1 : 0);
})();
