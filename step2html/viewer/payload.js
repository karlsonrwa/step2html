// ==== payload: the bytes the page carries, checked before anything is drawn.
//
// One raw-deflated, base64 block with its length and CRC32 written beside
// it. Both are checked BEFORE the first draw, and damage is reported instead
// of drawing something untrue - which is the one thing a 3D PDF cannot do,
// since a damaged PDF simply fails to open. The layout is the S3DH header of
// payload.py, and the two must agree on every offset.
const T=(()=>{const t=new Uint32Array(256);for(let n=0;n<256;n++){let c=n;
  for(let k=0;k<8;k++)c=c&1?0xEDB88320^(c>>>1):c>>>1;t[n]=c>>>0}return t})();
// The CRC as a running value, so it can be fed the inflated chunks as they
// arrive instead of making a second pass over the whole; crc32(b) is the
// same thing over one buffer, and what the tests check.
function crcRun(c,b){for(let i=0;i<b.length;i++)c=T[(c^b[i])&255]^(c>>>8);return c}
function crc32(b){return (crcRun(0xFFFFFFFF,b)^0xFFFFFFFF)>>>0}

// One turn of the event loop, so the page can paint what it has just been
// told. A posted message, not setTimeout: nested timers are clamped to four
// milliseconds each, and a thousand chunks would spend four seconds waiting.
// Not requestAnimationFrame either - an embedded or offscreen view may never
// run a frame callback, and a loader that waited for one would hang there.
const breath=(()=>{
  if(typeof MessageChannel==='undefined') return ()=>new Promise(r=>setTimeout(r,0));
  const ch=new MessageChannel(); let waiting=[];
  ch.port1.onmessage=()=>{const w=waiting; waiting=[]; w.forEach(r=>r());};
  return ()=>new Promise(r=>{waiting.push(r); ch.port2.postMessage(0);});
})();

// The base64 undone and inflated, or a throw with a kind: 'old' where the
// browser cannot do it at all, 'unpack' where the bytes will not inflate.
// Two questions, asked apart, because they have different answers. The API
// arrived in Chrome 80 but the deflate-raw FORMAT only in 103, and a browser
// in between throws from the constructor - inside the same try as the
// unpacking, that read as "damaged file" about a file that was whole.
//
// -> {bin, crc}: the bytes, and their CRC32 run over them as they came.
// *expect* is the length the page promises, for the counter; *progress*
// is told ('decode', 0..1) while the base64 is read and ('inflate', 0..1)
// while the bytes come out, and the page may paint between calls.
//
// The base64 step was the whole of the waiting once: written as
// Uint8Array.from(atob(b64), c=>c.charCodeAt(0)) it made a one-character
// string and a call for every byte - 3.1 s for the 18 MB of a 24 MB page,
// against 0.3 s to inflate them and 0.2 s to check them. A plain loop over
// charCodeAt does the same in 0.1 s (docs/performance.md). In slices, with a
// breath between, so the counter moves while it runs.
async function inflate(b64,expect,progress){
  progress=progress||(()=>{});
  if(!('DecompressionStream' in window)) throw {kind:'old'};
  let ds;
  try{ ds=new DecompressionStream('deflate-raw'); }catch(e){ throw {kind:'old'}; }
  try{
    const bs=atob(b64), n=bs.length, packed=new Uint8Array(n), SLICE=1<<22;
    for(let i=0;i<n;i+=SLICE){
      const end=Math.min(n,i+SLICE);
      for(let j=i;j<end;j++) packed[j]=bs.charCodeAt(j);
      progress('decode',end/n); await breath();
    }
    // Inflated chunk by chunk as the stream hands them over, the CRC run
    // over each as it arrives, and the counter told how far along the
    // promised length the bytes have got.
    const reader=new Blob([packed]).stream().pipeThrough(ds).getReader();
    const parts=[]; let got=0, crc=0xFFFFFFFF, told=-1;
    for(;;){
      const {done,value}=await reader.read();
      if(done) break;
      parts.push(value); got+=value.length; crc=crcRun(crc,value);
      const f=expect>0?Math.min(1,got/expect):0, step=Math.floor(f*100);
      if(step!==told){ told=step; progress('inflate',f); await breath(); }
    }
    progress('inflate',1);
    const bin=new Uint8Array(got); let o=0;
    for(const p of parts){ bin.set(p,o); o+=p.length; }
    return {bin,crc:(crc^0xFFFFFFFF)>>>0};
  }catch(e){ throw {kind:'unpack'}; }
}

// What this page can read: the magic payload.py writes and the format
// version it was written against. The two must agree with payload.py's
// MAGIC and FORMAT_VERSION.
const MAGIC='S3DH', FORMAT=4;

// The header and the arrays behind it, as typed views. After the magic and
// the version: seven counts and four floats, then the arrays in the order
// the counts name them.
//
// The first eight bytes are ASKED, not assumed. Every count below is read
// from a fixed offset, so bytes that are not a payload at all - another
// file pasted in, a page written by a newer tool - came out as enormous
// array lengths and the page then reported a damaged file, or drew
// nothing, about a file that is whole and simply not this format. Thrown
// with a kind, the way inflate does: boot.js turns each into words.
function parsePayload(bin){
  const dv=new DataView(bin.buffer,bin.byteOffset,bin.byteLength);
  if(bin.length<48) throw {kind:'magic',got:'too short'};
  const magic=String.fromCharCode(dv.getUint8(0),dv.getUint8(1),
                                  dv.getUint8(2),dv.getUint8(3));
  if(magic!==MAGIC) throw {kind:'magic',got:magic};
  const ver=dv.getUint32(4,true);
  if(ver!==FORMAT) throw {kind:'version',got:ver};
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
