// ==== payload: the bytes the page carries, checked before anything is drawn.
//
// One raw-deflated, base64 block with its length and CRC32 written beside
// it. Both are checked BEFORE the first draw, and damage is reported instead
// of drawing something untrue - which is the one thing a 3D PDF cannot do,
// since a damaged PDF simply fails to open. The layout is the S3DH header of
// payload.py, and the two must agree on every offset.
const T=(()=>{const t=new Uint32Array(256);for(let n=0;n<256;n++){let c=n;
  for(let k=0;k<8;k++)c=c&1?0xEDB88320^(c>>>1):c>>>1;t[n]=c>>>0}return t})();
function crc32(b){let c=0xFFFFFFFF;for(let i=0;i<b.length;i++)
  c=T[(c^b[i])&255]^(c>>>8);return (c^0xFFFFFFFF)>>>0}

// The base64 undone and inflated, or a throw with a kind: 'old' where the
// browser cannot do it at all, 'unpack' where the bytes will not inflate.
// Two questions, asked apart, because they have different answers. The API
// arrived in Chrome 80 but the deflate-raw FORMAT only in 103, and a browser
// in between throws from the constructor - inside the same try as the
// unpacking, that read as "damaged file" about a file that was whole.
async function inflate(b64){
  if(!('DecompressionStream' in window)) throw {kind:'old'};
  let ds;
  try{ ds=new DecompressionStream('deflate-raw'); }catch(e){ throw {kind:'old'}; }
  try{
    const packed=Uint8Array.from(atob(b64),c=>c.charCodeAt(0));
    const buf=await new Response(new Blob([packed]).stream().pipeThrough(ds)).arrayBuffer();
    return new Uint8Array(buf);
  }catch(e){ throw {kind:'unpack'}; }
}

// The header and the arrays behind it, as typed views. After the magic and
// the version: seven counts and four floats, then the arrays in the order
// the counts name them.
function parsePayload(bin){
  const dv=new DataView(bin.buffer,bin.byteOffset,bin.byteLength);
  const nv=dv.getUint32(8,true), ni=dv.getUint32(12,true),
        nev=dv.getUint32(16,true), nei=dv.getUint32(20,true),
        nfa=dv.getUint32(24,true), ncr=dv.getUint32(28,true),
        span=dv.getFloat32(32,true);
  const half=[dv.getFloat32(36,true),dv.getFloat32(40,true),dv.getFloat32(44,true)];
  const buf=bin.buffer;
  let o=bin.byteOffset+48;
  const pos=new Float32Array(buf.slice(o,o+nv*12)); o+=nv*12;
  const nrmB=new Uint8Array(buf.slice(o,o+nv*3)); o+=nv*3;
  const colB=new Uint8Array(buf.slice(o,o+nv*3)); o+=nv*3;
  const idx=new Uint32Array(buf.slice(o,o+ni*4)); o+=ni*4;
  const epos=new Float32Array(buf.slice(o,o+nev*12)); o+=nev*12;
  const eidx=new Uint32Array(buf.slice(o,o+nei*4)); o+=nei*4;
  // Where each face's triangles start, in triangles: one number per face,
  // because a face's triangles are one contiguous run.
  const faceAt=new Uint32Array(buf.slice(o,o+nfa*4)); o+=nfa*4;
  // Seven floats each: centre, axis, radius. This is what a measurement snaps
  // to - the centre of a hole or of a pin, which is the number that is
  // actually wanted and the one that cannot be hit by eye.
  const cir=new Float32Array(buf.slice(o,o+ncr*28));
  return {nv,ni,nev,nei,nfa,ncr,span,half,pos,nrmB,colB,idx,epos,eidx,faceAt,cir};
}
