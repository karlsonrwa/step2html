// ==== hash: the view in the address, so a link to it is a copy away.

// Trailing zeros go only from a FRACTION. Stripping them off the whole
// string turned 120000 into 12 - toPrecision(6) gives that one no
// decimal point to stop at, unlike 1200, which comes back as "1200.00"
// and survives. The symptom would have been a link that quietly
// restores a different view.
function encodeView(cam){
  const n=v=>(+v).toPrecision(6).replace(/(\.\d*?)0+$/,'$1')
                                .replace(/\.$/,'');
  const bits=[...cam.rot.slice(0,3),...cam.rot.slice(4,7),
              ...cam.rot.slice(8,11), cam.dist, cam.oh, cam.px, cam.py,
              ...cam.pivot].map(n).join(',');
  return '#v='+bits;
}

// The camera a hash describes, or null for anything else. "+" belongs in
// the character class: past a million toPrecision returns "1.00000e+6", and
// a class without it rejects the page's own output. Nine numbers for the
// rotation, then dist, oh, px, py, and three for the pivot - counted wrong
// once, and the only symptom was a link that silently did not restore
// anything.
function decodeView(hash){
  const m=/^#v=([-+\d.,e]+)$/.exec(hash||'');
  if(!m) return null;
  const p=m[1].split(',').map(Number);
  if(p.length!==16||p.some(Number.isNaN)) return null;
  return {rot:new Float32Array([p[0],p[1],p[2],0, p[3],p[4],p[5],0,
                                p[6],p[7],p[8],0, 0,0,0,1]),
          dist:p[9], oh:p[10], px:p[11], py:p[12],
          pivot:[p[13],p[14],p[15]]};
}
