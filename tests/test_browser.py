"""The page in a real browser: what only the DOM and the framebuffer say.

test_page reads the page as text and test_viewer runs the modules that have
no document in them. Between the two sits half the viewer - boot.js, gl.js,
measure.js, png.js, overlays.js - which was checked by grepping the page for
words. A word in a file is not a behaviour: every one of those greps passes
against code that does the opposite.

So this opens the REAL page, the one convert() writes from the shipped
viewer/ files, in headless Chrome (Edge where there is no Chrome), and reads
the answers out of the DOM. A probe script is spliced in AHEAD of the page's
own script - so it can watch the loading counter from its first write - and
it drives the page with the events a user would send, then writes one JSON
blob into a hidden <pre> that --dump-dom brings back here. Every field below
becomes a check with the number it was measured from.

What makes this possible without a driver:
  * --virtual-time-budget runs the page's timers as fast as they can go and
    advances the clock with them, so the 400 ms the address waits is both
    measurable and instant;
  * the camera is READABLE from outside: the page writes it into the address
    as sixteen numbers, and decodeView reads them back;
  * a draw can be forced synchronously (a change event on the projection
    radio the page is already on), and readPixels in that same task sees the
    frame before it is composited away - which is how a pixel oracle is
    possible at all on a canvas with no preserveDrawingBuffer.

Where neither browser is installed this says so and passes, the way
test_viewer does without node.
"""
from __future__ import annotations

import base64
import concurrent.futures
import html as htmlmod
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path

from harness import check, run, scratch
from fixtures import coloured_assembly
from step2html import payload
from step2html.convert import Options, convert

# Chrome first - it is the browser the user works in - and Edge second,
# which is on every Windows 11. Both were measured to run this identically
# (Chrome 153, Edge 153, 21 Sep 2026).
CANDIDATES = (
    r"{pf}\Google\Chrome\Application\chrome.exe",
    r"{pf86}\Google\Chrome\Application\chrome.exe",
    r"{pf86}\Microsoft\Edge\Application\msedge.exe",
    r"{pf}\Microsoft\Edge\Application\msedge.exe",
)
WINDOW = "900,700"           # the canvas comes out 748 x 604 at dpr 1
BUDGET = 20000               # ms of VIRTUAL time; the probe spends about 11
MARK = "\n<script>\n"        # the page's one script, which the probe goes before


def browser() -> Path | None:
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    for pattern in CANDIDATES:
        path = Path(pattern.format(pf=pf, pf86=pf86))
        if path.is_file():
            return path
    return None


def splice(page: str, js: str) -> str:
    """The page with `js` as a script of its own, ahead of the page's."""
    at = page.index(MARK)
    return page[:at] + MARK + js + "</script>" + page[at:]


def repack(page: str, change) -> str:
    """The page with its payload bytes put through `change`.

    The recorded length and CRC are rewritten to match, so the page is a
    healthy one that simply carries other bytes - which is what a file in
    another format is. Hand back (body, False) to leave them as they were
    and make the damage detectable instead.
    """
    b64 = re.search(r'id="geo">([^<]+)<', page).group(1).strip()
    body = payload.decode(b64)
    out = change(body)
    body, restamp = out if isinstance(out, tuple) else (out, True)
    comp = zlib.compressobj(9, zlib.DEFLATED, -15)
    packed = base64.b64encode(comp.compress(body) + comp.flush()).decode("ascii")
    page = page.replace(b64, packed)
    if restamp:
        page = re.sub(r"const CRC=\d+", f"const CRC={zlib.crc32(body) & 0xFFFFFFFF}",
                      page)
        page = re.sub(r"RAW=\d+", f"RAW={len(body)}", page)
    return page


def strip_edges(body: bytes) -> bytes:
    """The same model with no edge lines in it: nei goes to nought."""
    nv, ni, nev, nei = struct.unpack_from("<4I", body, 8)
    at = 48 + nv * 12 + nv * 3 + nv * 3 + ni * 4 + nev * 12
    out = bytearray(body)
    del out[at:at + nei * 4]
    struct.pack_into("<I", out, 20, 0)
    return bytes(out)


def ascii_only(text: str) -> str:
    return str(text).encode("ascii", "replace").decode("ascii")


def dom(exe: Path, page: Path, profile: Path, fragment: str = "",
        extra: tuple = ()) -> str:
    """The page's DOM after its scripts have run, as the browser prints it."""
    cmd = [str(exe), "--headless=new", "--disable-gpu",
           "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
           "--no-first-run", "--no-default-browser-check",
           f"--user-data-dir={profile}", f"--window-size={WINDOW}",
           f"--virtual-time-budget={BUDGET}", "--dump-dom", *extra,
           page.as_uri() + fragment]
    # Generous, and caught rather than raised: under a mutation run there
    # are two suites and four browsers on this machine at once, and a browser
    # that never answers should read as a page that said nothing, not as a
    # traceback out of a worker thread.
    try:
        done = subprocess.run(cmd, capture_output=True, timeout=300,
                              encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return ""
    return done.stdout or ""


def answer(text: str) -> dict:
    """The probe's JSON out of the dumped DOM."""
    m = re.search(r'<pre id="probeout"[^>]*>(.*?)</pre>', text, re.S)
    if not m:
        return {"missing": text[-400:]}
    return json.loads(htmlmod.unescape(m.group(1)))


# --------------------------------------------------------------------------- #
# The probe: everything the page is asked, in one load. It talks to the page
# the way a user does - pointer, wheel, key and change events - and reads the
# answers where they can be read: the address, the DOM, and the framebuffer.
# A synthetic pointer is not an active pointer, so setPointerCapture refuses
# one and is stubbed out here; nothing else of the browser is replaced.
# --------------------------------------------------------------------------- #
PROBE = r"""
(function(){
'use strict';
const R={errors:{}};
const pct=[];
const lp=document.getElementById('loadpct');
new MutationObserver(recs=>{for(const _ of recs) pct.push(lp.textContent);})
  .observe(lp,{childList:true,characterData:true,subtree:true});
Element.prototype.setPointerCapture=function(){};
Element.prototype.releasePointerCapture=function(){};
const saved={};
const realURL=URL.createObjectURL.bind(URL);
URL.createObjectURL=function(b){saved.blob=b;return realURL(b);};
HTMLAnchorElement.prototype.click=function(){saved.name=this.download;};
// The canvas savePng composed, caught while it is still there: decoding the
// blob back needs createImageBitmap, whose promise never settles once
// virtual time has run out.
const realToBlob=HTMLCanvasElement.prototype.toBlob;
HTMLCanvasElement.prototype.toBlob=function(cb,type){
  saved.data=this.getContext('2d').getImageData(0,0,this.width,this.height);
  saved.size=[this.width,this.height];
  return realToBlob.call(this,cb,type);
};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
function say(){
  let pre=document.getElementById('probeout');
  if(!pre){ pre=document.createElement('pre'); pre.id='probeout';
            // Out of the layout: a wide block in the body changes what the
            // bar measures and moves the canvas under the probe's feet.
            pre.style.display='none'; document.body.appendChild(pre); }
  pre.textContent=JSON.stringify(R);
}
addEventListener('error',e=>{
  R.errors.window=(R.errors.window||'')+e.message+' @'+e.lineno+';'; say();});
addEventListener('unhandledrejection',e=>{
  R.errors.reject=String(e.reason&&e.reason.stack||e.reason).slice(0,300); say();});
async function until(cond,tries){
  for(let i=0;i<tries;i++){ if(cond()) return true; await sleep(20); }
  return false;
}
async function step(name,fn){
  // Fresh for every step: a rectangle read once at boot and kept is half a
  // pixel out by the time the bar has wrapped, and half a pixel is a fifth
  // of the three-pixel click below.
  RECT=cv.getBoundingClientRect();
  const t0=performance.now();
  try{ R[name]=await fn(); }
  catch(e){ R.errors[name]=String(e&&e.stack||e).slice(0,300); }
  (R.ms=R.ms||{})[name]=Math.round(performance.now()-t0);
  say();
}
const cv=document.getElementById('cv');
const gl=cv.getContext('webgl2',{antialias:true});
const dpr=Math.min(devicePixelRatio||1,2);
const round3=v=>+v.toFixed(3);
function forceDraw(){
  document.querySelector('input[name=proj]:checked')
          .dispatchEvent(new Event('change',{bubbles:true}));
}
function readPx(sx,sy){
  const p=new Uint8Array(4);
  gl.readPixels(Math.round(sx*dpr),cv.height-1-Math.round(sy*dpr),1,1,
                gl.RGBA,gl.UNSIGNED_BYTE,p);
  return [p[0],p[1],p[2]];
}
function frame(){
  const p=new Uint8Array(cv.width*cv.height*4);
  gl.readPixels(0,0,cv.width,cv.height,gl.RGBA,gl.UNSIGNED_BYTE,p);
  return p;
}
function count(px,col,tol){
  let n=0;
  for(let i=0;i<px.length;i+=4)
    if(Math.abs(px[i]-col[0])<=tol&&Math.abs(px[i+1]-col[1])<=tol
       &&Math.abs(px[i+2]-col[2])<=tol) n++;
  return n;
}
const big=c=>c[0]>=c[1]&&c[0]>=c[2]?0:(c[1]>=c[2]?1:2);
const camNow=()=>decodeView(location.hash);
const isOrtho=()=>document.querySelector('input[name=proj]:checked').value==='ortho';
const radio=(name,value)=>{
  const r=[...document.querySelectorAll('input[name='+name+']')]
      .find(x=>x.value===value);
  r.checked=true; r.dispatchEvent(new Event('change',{bubbles:true}));
};
function mats(cam){
  return {MV:modelView(cam),
          P:projection(cam,isOrtho(),cv.clientWidth/cv.clientHeight,SPAN)};
}
function key(k,opts){
  dispatchEvent(new KeyboardEvent('keydown',
      Object.assign({key:k,bubbles:true},opts||{})));
}
function ptr(type,x,y,opts){
  cv.dispatchEvent(new PointerEvent(type,Object.assign(
    {pointerId:1,clientX:x,clientY:y,button:0,buttons:1,
     bubbles:true,cancelable:true,isPrimary:true},opts||{})));
}
async function hashChange(before,tries){
  await until(()=>location.hash!==before,tries||60);
  return location.hash;
}
// A named view, waited for by WHAT the address says rather than by the fact
// that it changed: pressing 1 when the page is already looking from the top
// changes nothing, and waiting for a change there is a second of virtual
// time spent on nothing - a second that costs real seconds, because the
// browser composites every frame of it in software.
async function view(n){
  key(String(n));
  const want=fitDist(VIEWS[n-1],Math.max(.2,cv.clientWidth/cv.clientHeight),
                     MESH.half);
  await until(()=>{const c=camNow();
    return c&&Math.abs(c.dist-want)<want*1e-4&&c.pivot.join()==='0,0,0';},60);
  return camNow();
}
let SPAN=0, MESH=null, RECT=null, GRID=[], HOVER=null;
addEventListener('load',()=>{main().catch(e=>{
  R.errors.main=String(e&&e.stack||e); say();});});

async function main(){
  say();
  R.booted=await until(
    ()=>document.getElementById('loading').style.display==='none',400);
  R.pct=pct.slice();
  R.gl=!!gl;
  if(gl){
    const dbg=gl.getExtension('WEBGL_debug_renderer_info');
    R.renderer=dbg?gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL)
                  :gl.getParameter(gl.RENDERER);
  }
  R.dpr=devicePixelRatio;
  R.canvas=[cv.clientWidth,cv.clientHeight,cv.width,cv.height];
  R.decompression=('DecompressionStream' in window);
  R.err=[document.getElementById('err').style.display,
         document.getElementById('errtext').textContent,
         cv.style.display];
  R.edgeDisabled=[...document.querySelectorAll('input[name=edge]')]
      .map(r=>r.disabled);
  R.title=document.title;
  say();
  if(!R.booted) return;

  // The payload again, read by the page's own reader, for the geometry this
  // probe has to aim at: which triangle is where, and where the rims are.
  const un=await inflate(document.getElementById('geo').textContent.trim(),RAW);
  MESH=parsePayload(un.bin);
  SPAN=MESH.span;
  R.mesh=[MESH.nv,MESH.ni,MESH.nev,MESH.nei,MESH.nfa,MESH.ncr,round3(MESH.span)];
  RECT=cv.getBoundingClientRect();
  await until(()=>location.hash.startsWith('#v='),60);
  R.hash0=location.hash;

  // ---- the address ---------------------------------------------------- #
  await step('debounce',async()=>{
    const before=location.hash, t0=performance.now();
    cv.dispatchEvent(new WheelEvent('wheel',
        {deltaY:120,bubbles:true,cancelable:true}));
    const immediate=location.hash===before;
    await hashChange(before);
    return {immediate,ms:Math.round(performance.now()-t0),
            history:history.length,
            ratio:+(camNow().dist/decodeView(before).dist).toFixed(5)};
  });

  // ---- the picture that leaves ------------------------------------------ #
  await step('png',async()=>{
    const out={};
    const marker=document.getElementById('pivot');
    const shoot=async()=>{
      saved.blob=null; saved.data=null;
      document.getElementById('png')
              .dispatchEvent(new MouseEvent('click',{bubbles:true}));
      await until(()=>!!saved.blob&&!!saved.data,100);
    };
    // The picture with no crosshair in it is taken first, with the centre of
    // rotation down: it is down already wherever this step runs, because
    // every way of showing it ends in a fade.
    await until(()=>!marker.classList.contains('on'),60);
    const at=[Math.round(RECT.width/2),Math.round(RECT.height/2)];
    out.markerBefore=marker.classList.contains('on');
    await shoot();
    const cold=saved.data;
    ptr('pointerdown',RECT.left+at[0],RECT.top+at[1]);
    ptr('pointerup',RECT.left+at[0],RECT.top+at[1]);
    out.markerOn=marker.classList.contains('on');
    const mx=parseFloat(marker.style.left), my=parseFloat(marker.style.top);
    out.marker=[mx,my];
    await shoot();
    out.name=saved.name;
    out.title=document.title+'.png';
    out.type=saved.blob&&saved.blob.type;
    out.bytes=saved.blob&&saved.blob.size;
    out.image=saved.size;
    out.canvas=[cv.width,cv.height];
    if(!saved.data||!cold) return out;
    const k=cv.width/cv.clientWidth;
    const grab=(d,x,y)=>{const o=((y*d.width)+x)*4;
                         return [d.data[o],d.data[o+1],d.data[o+2]];};
    const arms=[[mx+9,my],[mx-9,my],[mx,my+9],[mx,my-9]];
    const diff=d=>arms.map(a=>{
      const png=grab(d,Math.round(a[0]*k),Math.round(a[1]*k));
      const live=readPx(a[0],a[1]);
      return Math.max(Math.abs(png[0]-live[0]),Math.abs(png[1]-live[1]),
                      Math.abs(png[2]-live[2]));
    });
    forceDraw();
    out.corner=[grab(saved.data,3,3),readPx(3,3)];
    out.crossOn=diff(saved.data);
    out.crossOff=diff(cold);
    // And that it DRAWS before it copies. In a page nobody composites the
    // drawing buffer is never emptied, so the missing frame cannot be seen
    // in the picture - but the buffer's SIZE can: the canvas is narrowed
    // without telling the page, so nothing has redrawn at the new size, and
    // gl.js resizes the buffer in the draw savePng asks for.
    document.body.style.width='600px';
    void cv.clientWidth;
    out.stale=[cv.width,Math.round(cv.clientWidth*dpr)];
    await shoot();
    out.afterStale=saved.size;
    out.wantStale=[Math.round(cv.clientWidth*dpr),
                   Math.round(cv.clientHeight*dpr)];
    document.body.style.width='';
    void cv.clientWidth;
    dispatchEvent(new Event('resize'));
    return out;
  });

  // ---- a drag turns about the axes of the SCREEN ----------------------- #
  await step('orbit',async()=>{
    const before=location.hash, rot0=decodeView(before).rot;
    const dx=40, dy=25;
    ptr('pointerdown',RECT.left+200,RECT.top+200);
    ptr('pointermove',RECT.left+200+dx,RECT.top+200+dy);
    ptr('pointerup',RECT.left+200+dx,RECT.top+200+dy);
    await hashChange(before);
    const got=camNow().rot;
    const pre=orthonormalise(mul(mul(rotX(dy*.008),rotY(dx*.008)),rot0));
    const post=orthonormalise(mul(rot0,mul(rotX(dy*.008),rotY(dx*.008))));
    const diff=m=>{let d=0;for(const i of [0,1,2,4,5,6,8,9,10])
                     d=Math.max(d,Math.abs(got[i]-m[i]));return +d.toFixed(6);};
    return {pre:diff(pre),post:diff(post)};
  });

  // ---- four pixels apart: a click, not a drag -------------------------- #
  await step('click',async()=>{
    const cam=await view(1);
    RECT=cv.getBoundingClientRect();
    const m=mats(cam);
    const at=[Math.round(RECT.width/2),Math.round(RECT.height/2)];
    const got=pick(MESH,cam,m.MV,isOrtho(),SPAN,RECT,
                   RECT.left+at[0]+3,RECT.top+at[1]);
    // The same ray at the pixel the pointer went DOWN on, three pixels to
    // the left: what the pivot would be if a click took the down position.
    const down=pick(MESH,cam,m.MV,isOrtho(),SPAN,RECT,
                    RECT.left+at[0],RECT.top+at[1]);
    const out={hit:got?got.hit.map(round3):null,
               down:down?down.hit.map(round3):null,
               px:round3(pxSize(cam,m.MV,isOrtho(),cv.clientHeight,
                                got?got.hit:[0,0,0]))};
    let before=location.hash;
    ptr('pointerdown',RECT.left+at[0],RECT.top+at[1]);
    ptr('pointermove',RECT.left+at[0]+3,RECT.top+at[1]);
    ptr('pointerup',RECT.left+at[0]+3,RECT.top+at[1]);
    await hashChange(before);
    out.pivot=camNow().pivot.map(round3);
    before=location.hash;
    ptr('pointerdown',RECT.left+at[0]+20,RECT.top+at[1]);
    ptr('pointermove',RECT.left+at[0]+30,RECT.top+at[1]);
    ptr('pointerup',RECT.left+at[0]+30,RECT.top+at[1]);
    await hashChange(before);
    out.afterDrag=camNow().pivot.map(round3);
    return out;
  });

  // ---- the keys -------------------------------------------------------- #
  await step('keys',async()=>{
    const out={};
    key('3');
    await hashChange(location.hash);
    const rot=camNow().rot;
    out.view3=[0,1,2,4,5,6,8,9,10].every(i=>Math.abs(rot[i]-VIEWS[2][i])<1e-4);
    const held=location.hash;
    key('1',{ctrlKey:true}); key('2',{altKey:true}); key('e',{metaKey:true});
    await sleep(600);
    out.modifierIgnored=location.hash===held
      && document.querySelector('input[name=edge]:checked').value==='on';
    key('e');
    out.edge=document.querySelector('input[name=edge]:checked').value;
    key('p');
    out.proj=document.querySelector('input[name=proj]:checked').value;
    key('p'); key('e');
    out.back=[document.querySelector('input[name=proj]:checked').value,
              document.querySelector('input[name=edge]:checked').value];
    key('m');
    out.measure=[document.getElementById('measure').checked,
                 document.getElementById('view').classList.contains('measuring')];
    key('m');
    out.measureOff=document.getElementById('measure').checked;
    document.getElementById('cube')
            .dispatchEvent(new MouseEvent('click',{bubbles:true}));
    out.menuOpen=document.getElementById('views').classList.contains('open');
    key('Escape');
    out.menuClosed=!document.getElementById('views').classList.contains('open')
                && !document.getElementById('scrim').classList.contains('open');
    return out;
  });

  // ---- a named view: home, then the view, then a fit ------------------- #
  await step('showView',async()=>{
    // From a moved camera, so "home first" has something to undo: the pivot
    // is wherever the click above left it.
    const cam=await view(5);
    const a=Math.max(.2,cv.clientWidth/cv.clientHeight);
    return {pivot:cam.pivot.map(round3), dist:round3(cam.dist),
            wantDist:round3(fitDist(VIEWS[4],a,MESH.half)),
            oh:round3(cam.oh), wantOh:round3(cam.dist*Math.tan(FOV/2)),
            rot:[0,1,2,4,5,6,8,9,10].every(i=>Math.abs(cam.rot[i]-VIEWS[4][i])<1e-4)};
  });

  // ---- the theme, the background and the colour of the edges ----------- #
  await step('theme',async()=>{
    const out={};
    out.sysDark=matchMedia('(prefers-color-scheme: dark)').matches;
    out.lightClass=document.documentElement.classList.contains('light');
    forceDraw();
    out.bgSystem=readPx(3,3);
    radio('theme','dark');
    out.darkClass=document.documentElement.classList.contains('light');
    forceDraw();
    out.bgDark=readPx(3,3);
    out.edgeDarkOn=count(frame(),[8,10,13],2);
    out.edgeLightInDark=count(frame(),[26,33,43],2);
    radio('theme','light');
    forceDraw();
    out.bgLight=readPx(3,3);
    out.edgeLightOn=count(frame(),[26,33,43],2);
    out.edgeDarkInLight=count(frame(),[8,10,13],2);
    radio('edge','off');
    forceDraw();
    out.edgeLightOff=count(frame(),[26,33,43],2);
    radio('edge','on');
    return out;
  });

  // ---- what is drawn, and where ---------------------------------------- #
  await step('pixels',async()=>{
    const cam=await view(1);
    const m=mats(cam);
    const out={};
    forceDraw();
    out.corner=readPx(3,3);
    const at=[Math.round(RECT.width/2),Math.round(RECT.height/2)];
    const got=pick(MESH,cam,m.MV,isOrtho(),SPAN,RECT,
                   RECT.left+at[0],RECT.top+at[1]);
    out.tri=got?got.tri:-1;
    if(got){
      const v0=MESH.idx[got.tri*3];
      out.vertexColour=[MESH.colB[v0*3],MESH.colB[v0*3+1],MESH.colB[v0*3+2]];
      forceDraw();
      out.pixel=readPx(at[0],at[1]);
      out.dominant=[big(out.vertexColour),big(out.pixel)];
      const back=toScreen(m.MV,m.P,cv.clientWidth,cv.clientHeight,got.hit);
      out.reproject=back&&[round3(back[0]-at[0]),round3(back[1]-at[1])];
      out.face=faceOfTriangle(MESH.faceAt,MESH.nfa,got.tri);
      out.at=at;
    }
    // A grid of points that hit the model, each with the face the page's
    // own ray says is under it. The highlight below must light up the
    // hovered face's points and NOT ONE of the others: a range that starts
    // a third of the way into the table still covers the face being
    // hovered, so "the hovered pixel went blue" alone proves nothing.
    const grid=[];
    for(let y=12;y<RECT.height-12;y+=19)
      for(let x=12;x<RECT.width-12;x+=23){
        const g=pick(MESH,cam,m.MV,isOrtho(),SPAN,RECT,RECT.left+x,RECT.top+y);
        if(!g) continue;
        grid.push({x,y,face:faceOfTriangle(MESH.faceAt,MESH.nfa,g.tri)});
      }
    forceDraw();
    for(const s of grid) s.px=readPx(s.x,s.y);
    GRID=grid;
    out.grid=grid.length;
    out.faces=[...new Set(grid.map(s=>s.face))].sort((a,b)=>a-b);
    // The face to hover is chosen in the MIDDLE of the visible ones, so
    // that one visible face comes before it in the table and one after: a
    // highlight that starts too early shows on the face before, one that
    // ends too late on the face after, and the face on top of the model -
    // the first one the eye lands on - would have caught neither, because
    // the faces around it in the table are not on screen at all.
    const seen=out.faces;
    HOVER=grid.find(s=>s.face===seen[Math.floor(seen.length/2)])||grid[0];
    out.hoverAt=HOVER&&{x:HOVER.x,y:HOVER.y,face:HOVER.face};
    const other=grid.find(s=>s.face!==out.face);
    out.other=other?{x:other.x,y:other.y,face:other.face}:null;
    if(other) out.otherPixel=other.px;
    return out;
  });

  // ---- the hovered face, and only it, lights up ------------------------ #
  await step('hover',async()=>{
    const out={};
    const meas=document.getElementById('measure');
    meas.checked=true; meas.dispatchEvent(new Event('change',{bubbles:true}));
    const at=[HOVER.x,HOVER.y];
    out.face=HOVER.face;
    out.at=at;
    await sleep(40);
    ptr('pointermove',RECT.left+at[0],RECT.top+at[1],{buttons:0});
    out.hoverPixel=readPx(at[0],at[1]);
    if(R.pixels.other) out.otherPixel=readPx(R.pixels.other.x,R.pixels.other.y);
    // Every point of the grid again, in the frame the hover just drew.
    const moved=[], still=[];
    for(const s of GRID){
      const now=readPx(s.x,s.y);
      const d=Math.max(Math.abs(now[0]-s.px[0]),Math.abs(now[1]-s.px[1]),
                       Math.abs(now[2]-s.px[2]));
      (d>8?moved:still).push(s.face);
    }
    out.movedFaces=[...new Set(moved)].sort((a,b)=>a-b);
    out.stillFaces=[...new Set(still)].sort((a,b)=>a-b);
    out.moved=moved.length;
    meas.checked=false; meas.dispatchEvent(new Event('change',{bubbles:true}));
    return out;
  });

  // ---- the centre of the turn is drawn where it is --------------------- #
  await step('marker',async()=>{
    const marker=document.getElementById('pivot');
    await view(1);
    const middle=[parseFloat(marker.style.left),parseFloat(marker.style.top)];
    // Panned first, so the centre of the turn is NOT in the middle of the
    // canvas: there every mapping agrees with every other and the marker
    // would sit right however it was placed.
    const before=location.hash;
    ptr('pointerdown',RECT.left+300,RECT.top+300,{shiftKey:true});
    ptr('pointermove',RECT.left+400,RECT.top+250,{shiftKey:true});
    ptr('pointerup',RECT.left+400,RECT.top+250,{shiftKey:true});
    await hashChange(before);
    const cam=camNow(), m=mats(cam);
    forceDraw();
    const want=toScreen(m.MV,m.P,cv.clientWidth,cv.clientHeight,cam.pivot);
    const out={middle, pan:[round3(cam.px),round3(cam.py)],
               left:parseFloat(marker.style.left),
               top:parseFloat(marker.style.top),
               want:want&&[round3(want[0]),round3(want[1])]};
    // Held up for the whole of a turn - showMarker(0) is "no fade at all" -
    // and let go of afterwards. A centre of rotation that goes out in the
    // middle of a drag is one nobody can see while it is being used.
    ptr('pointerdown',RECT.left+300,RECT.top+300);
    out.heldAtOnce=marker.classList.contains('on');
    await sleep(700);
    out.heldLater=marker.classList.contains('on');
    ptr('pointermove',RECT.left+400,RECT.top+300);
    ptr('pointerup',RECT.left+400,RECT.top+300);
    await sleep(600);
    out.afterDrag=marker.classList.contains('on');
    return out;
  });

  // ---- the axis triad --------------------------------------------------- #
  await step('axes',async()=>{
    // An isometric view, where the three arms are at three different depths
    // and none is degenerate: from the top two of them lie in the plane of
    // the screen and the third points straight at the viewer, and any order
    // of drawing would look the same.
    const rot=(await view(7)).rot;
    forceDraw();
    const svg=document.getElementById('axes');
    const out={order:[...svg.children].map(e=>e.tagName+'.'+e.getAttribute('class'))};
    out.arms={};
    for(const c of ['x','y','z']){
      const ln=svg.querySelector('line.'+c);
      out.arms[c]=[+ln.getAttribute('x1'),+ln.getAttribute('y1'),
                   round3(+ln.getAttribute('x2')),round3(+ln.getAttribute('y2'))];
    }
    const arm=i=>{const v=[0,0,0];v[i]=1;
      return [rot[0]*v[0]+rot[4]*v[1]+rot[8]*v[2],
              rot[1]*v[0]+rot[5]*v[1]+rot[9]*v[2],
              rot[2]*v[0]+rot[6]*v[1]+rot[10]*v[2]];};
    const arms=[0,1,2].map(i=>({c:'xyz'[i],v:arm(i)}));
    out.want={};
    for(const a of arms)
      out.want[a.c]=[44,44,round3(44+a.v[0]*30),round3(44-a.v[1]*30)];
    out.wantOrder=[].concat(...arms.slice().sort((p,q)=>p.v[2]-q.v[2])
                                 .map(a=>['line.'+a.c,'text.'+a.c]));
    out.natural=['line.x','text.x','line.y','text.y','line.z','text.z'];
    out.depth=arms.map(a=>round3(a.v[2]));
    return out;
  });

  // ---- two points, a reading, and the legs of the path ----------------- #
  await step('measure',async()=>{
    const out={};
    const cam=await view(1);
    const m=mats(cam);
    const meas=document.getElementById('measure');
    meas.checked=true; meas.dispatchEvent(new Event('change',{bubbles:true}));
    const tol=hit=>SNAP_PX*pxSize(cam,m.MV,isOrtho(),cv.clientHeight,hit);
    // Two pixels on the model that catch no rim, so what each click takes
    // is the point the ray hit and the reading is the distance between them.
    const spots=[];
    for(let y=40;y<RECT.height-40&&spots.length<2;y+=29)
      for(let x=40;x<RECT.width-40;x+=53){
        const g=pick(MESH,cam,m.MV,isOrtho(),SPAN,RECT,RECT.left+x,RECT.top+y);
        if(!g||snapAt(MESH.cir,MESH.ncr,g.hit,tol(g.hit))) continue;
        if(spots.length&&Math.hypot(spots[0].x-x,spots[0].y-y)<150) continue;
        spots.push({x,y,hit:g.hit});
        break;
      }
    out.spots=spots.map(s=>[s.x,s.y,s.hit.map(round3)]);
    if(spots.length<2) return out;
    const mlabel=document.getElementById('mlabel'),
          mline=document.getElementById('mline');
    const click=s=>{ptr('pointerdown',RECT.left+s.x,RECT.top+s.y);
                    ptr('pointerup',RECT.left+s.x,RECT.top+s.y);};
    click(spots[0]);
    out.afterOne=[mlabel.classList.contains('on'),
                  mline.classList.contains('on')];
    click(spots[1]);
    out.label=mlabel.textContent;
    out.labelOn=mlabel.classList.contains('on');
    const d=[0,1,2].map(i=>spots[1].hit[i]-spots[0].hit[i]);
    out.want=Math.hypot(d[0],d[1],d[2]).toFixed(3)+' mm\n'
            +['X','Y','Z'].map((ax,i)=>{const n=Math.abs(d[i])<5e-4?0:d[i];
               return '\u0394'+ax+' '+(n>0?'+':'')+n.toFixed(3);}).join('   ');
    out.legs=[...mline.querySelectorAll('line.ax')].map(l=>l.style.display);
    out.tags=[...mline.querySelectorAll('text.ax')].map(t=>t.textContent);
    out.wantTags=d.map(v=>Math.abs(v)>5e-3?Math.abs(v).toFixed(3):'');
    out.lead=mline.querySelector('line.lead').style.display;
    // the reading, dragged far out of the view, clamped back into it
    const lw=mlabel.offsetWidth, lh=mlabel.offsetHeight;
    const drag=(type,x,y)=>mlabel.dispatchEvent(new PointerEvent(type,
        {pointerId:2,clientX:x,clientY:y,bubbles:true,cancelable:true}));
    drag('pointerdown',RECT.left+200,RECT.top+200);
    drag('pointermove',RECT.left+5000,RECT.top+5000);
    drag('pointerup',RECT.left+5000,RECT.top+5000);
    out.dragged=[parseFloat(mlabel.style.left),parseFloat(mlabel.style.top)];
    out.wantDragged=[cv.clientWidth-lw/2-2,cv.clientHeight-lh/2-2];
    // a third click starts a fresh measurement rather than adding to one
    click(spots[0]);
    out.afterThird=[mlabel.classList.contains('on'),
                    mline.querySelector('line.main').style.display];
    click(spots[1]);
    out.beforeEscape=mlabel.classList.contains('on');
    key('Escape');
    out.afterEscape=[mlabel.classList.contains('on'),
                     mline.querySelector('line.main').style.display];
    // A leg of twenty microns, which no click can place: below half of the
    // last digit the reading shows, and therefore printed as a plain nought
    // with no sign at all. The page's own overlay painter, over the page's
    // own elements - there is no other way to hand it two points that close
    // together, and "0.000" against "+0.000" is the whole of the rule.
    const project=q=>toScreen(m.MV,m.P,cv.clientWidth,cv.clientHeight,q);
    paintMeasure({cv,mline,mlabel,marks:[[0,0,0],[8,0,2e-5]],
                  markCir:[null,null],measuring:true,hoverPoint:null,
                  cursor:null,snapNow:null,labelAt:null,project,
                  furniture:[]});
    out.tiny=mlabel.textContent;
    // The ring the press put up. Every pointerdown on the canvas shows the
    // centre of rotation with no fade at all, because a turn may be starting
    // - but a click in measuring mode places a point and moves no centre, so
    // there is nothing for the ring to stay up for. It used to stay until
    // the next ordinary release, and went into a saved picture with it.
    const marker=document.getElementById('pivot');
    ptr('pointerdown',RECT.left+spots[0].x,RECT.top+spots[0].y);
    out.ringDown=marker.classList.contains('on');
    ptr('pointerup',RECT.left+spots[0].x,RECT.top+spots[0].y);
    out.ringAtOnce=marker.classList.contains('on');
    await sleep(500);
    out.ringAfter=marker.classList.contains('on');
    out.ringOpacity=getComputedStyle(marker).opacity;
    meas.checked=false; meas.dispatchEvent(new Event('change',{bubbles:true}));
    return out;
  });

  // ---- the rim a click would take -------------------------------------- #
  await step('rim',async()=>{
    const out={};
    const cam=await view(1);
    const m=mats(cam);
    const meas=document.getElementById('measure');
    meas.checked=true; meas.dispatchEvent(new Event('change',{bubbles:true}));
    // The topmost circle of the payload and a point just inside its rim: in
    // the top view that is the pin's end face, the nearest surface there.
    let best=0;
    for(let i=1;i<MESH.ncr;i++) if(MESH.cir[i*7+2]>MESH.cir[best*7+2]) best=i;
    const o=best*7, r=MESH.cir[o+6];
    const s=toScreen(m.MV,m.P,cv.clientWidth,cv.clientHeight,
                     [MESH.cir[o]+r*.85,MESH.cir[o+1],MESH.cir[o+2]]);
    out.circle=[round3(MESH.cir[o]),round3(MESH.cir[o+1]),
                round3(MESH.cir[o+2]),round3(r)];
    await sleep(40);
    ptr('pointermove',RECT.left+s[0],RECT.top+s[1],{buttons:0});
    const mline=document.getElementById('mline');
    const rim=mline.querySelectorAll('polyline.rim')[0];
    const pts=(rim.getAttribute('points')||'').trim();
    out.points=pts?pts.split(/\s+/).length:0;
    out.rimShown=rim.style.display;
    const snapC=mline.querySelector('circle.snap');
    out.snapShown=snapC.style.display;
    out.snapAt=[round3(+snapC.getAttribute('cx')),round3(+snapC.getAttribute('cy'))];
    const c=toScreen(m.MV,m.P,cv.clientWidth,cv.clientHeight,
                     [MESH.cir[o],MESH.cir[o+1],MESH.cir[o+2]]);
    out.wantSnapAt=c&&[round3(c[0]),round3(c[1])];
    meas.checked=false; meas.dispatchEvent(new Event('change',{bubbles:true}));
    return out;
  });

  // ---- a camera moved by hand is not refitted --------------------------- #
  await step('touched',async()=>{
    const out={};
    const body=document.body;
    // The canvas is narrowed and the window told so. A resize event, not the
    // observer on the body: the observer answers on a frame, and a headless
    // page that nobody composites produces those when it pleases, while the
    // event is the page's other way in and arrives at once.
    const resize=w=>{ body.style.width=w;
                      void cv.clientWidth;            // lay it out first
                      dispatchEvent(new Event('resize')); };
    cv.dispatchEvent(new WheelEvent('wheel',
        {deltaY:-120,bubbles:true,cancelable:true}));
    await hashChange(location.hash);
    const moved=camNow().dist;
    resize('700px');
    out.width=[cv.clientWidth,cv.clientHeight];
    await sleep(500);
    out.keptAfterResize=[round3(moved),round3(camNow().dist)];
    // a double click forgets the hand-moved camera...
    let before=location.hash;
    cv.dispatchEvent(new MouseEvent('dblclick',{bubbles:true}));
    await hashChange(before);
    out.home=[round3(camNow().dist),
              round3(fitDist(HOME_ROT,
                             Math.max(.2,cv.clientWidth/cv.clientHeight),
                             MESH.half))];
    // ...so the next resize fits the model to the new canvas again
    before=location.hash;
    resize('500px');
    out.width2=[cv.clientWidth,cv.clientHeight];
    await hashChange(before,120);
    out.refitted=[round3(camNow().dist),
                  round3(fitDist(HOME_ROT,
                                 Math.max(.2,cv.clientWidth/cv.clientHeight),
                                 MESH.half))];
    resize('');
    await sleep(80);
    return out;
  });
  say();
}
})();
"""

# A page that is not expected to draw at all, or one loaded only to see what
# it made of its address: what the DOM says once it has settled, and nothing
# else.
GATE = r"""
(function(){
'use strict';
const R={};
const pct=[];
const lp=document.getElementById('loadpct');
new MutationObserver(recs=>{for(const _ of recs) pct.push(lp.textContent);})
  .observe(lp,{childList:true,characterData:true,subtree:true});
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
addEventListener('load',async()=>{
  const cv=document.getElementById('cv');
  for(let i=0;i<400;i++){
    if(document.getElementById('loading').style.display==='none') break;
    await sleep(20);
  }
  // A page opened AT a #v= address already has one, so waiting for the
  // address to appear proves nothing: what is waited for is the page's own
  // write, 400 ms after its first frame. It writes the same characters back
  // when it restored the view and the home camera's when it did not.
  await sleep(__SETTLE__);
  for(let i=0;i<60&&!location.hash.startsWith('#v=');i++) await sleep(20);
  R.pct=pct;
  R.err=document.getElementById('err').style.display;
  R.text=document.getElementById('errtext').textContent;
  R.canvas=cv.style.display;
  R.edgeDisabled=[...document.querySelectorAll('input[name=edge]')]
      .map(r=>r.disabled);
  R.hash=location.hash;
  R.title=document.title;
  const pre=document.createElement('pre');
  pre.id='probeout'; pre.style.display='none';
  pre.textContent=JSON.stringify(R);
  document.body.appendChild(pre);
});
})();
"""

# A hand-written address, restored at boot: an odd distance, a pan, a pivot
# away from the origin and a rotation that is not the identity. Every field
# survives toPrecision(6) unchanged, so what comes back must be this again,
# character for character - the home camera's numbers are nothing like it.
VIEW = ("#v=0.825336,0,-0.564642,0,1,0,0.564642,0,0.825336,"
        "137.25,35.5,-2.5,4.25,10,-20,30")


def main():
    exe = browser()
    if not exe:
        print("  note  neither Chrome nor Edge is installed here; the page was "
              "not opened in a browser")
        return
    with scratch("browser-") as tmp:
        work = Path(tmp)
        step = coloured_assembly(work / "fixture.step")
        out = work / "fixture.html"
        convert(Options(step=str(step), out=str(out), max_bytes="none",
                        deflection="0.04", angle=15.0))
        page = out.read_text(encoding="utf-8")

        # name -> (the page, the address it is opened at, extra flags)
        pages = {
            "main": (splice(page, PROBE), "", ()),
            # The one page that has to wait: see __SETTLE__ in GATE.
            "view": (splice(page, GATE.replace("__SETTLE__", "900")), VIEW, ()),
            # A browser with no WebGL at all: the page says so, in those
            # words, rather than dying on a null context.
            "nogl": (splice(page, GATE), "", ("--disable-3d-apis",)),
            # A whole file whose bytes are not the ones the page promises:
            # it inflates, and the CRC does not match.
            "crc": (splice(repack(page, lambda b: (b[:64] + bytes([b[64] ^ 0xFF])
                                                   + b[65:], False)), GATE), "", ()),
            # Not a payload of this tool's at all, and a payload of a format
            # this page was not written to read.
            "magic": (splice(repack(page, lambda b: b"XXXX" + b[4:]), GATE),
                      "", ()),
            "version": (splice(repack(page, lambda b: b[:4]
                                      + struct.pack("<I", 5) + b[8:]), GATE),
                        "", ()),
            # A model with no edge lines: the edge radios have nothing to do.
            "noedge": (splice(repack(page, strip_edges), GATE), "", ()),
        }
        pages = {name: (text.replace("__SETTLE__", "0"), fragment, extra)
                 for name, (text, fragment, extra) in pages.items()}
        got = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            jobs = {}
            for name, (text, fragment, extra) in pages.items():
                path = work / f"{name}.html"
                path.write_text(text, encoding="utf-8")
                profile = work / f"profile-{name}"
                jobs[name] = pool.submit(dom, exe, path, profile, fragment,
                                         extra)
            for name, job in jobs.items():
                got[name] = answer(job.result())
        r = got["main"]
        if "missing" in r:
            check(False, "the probe answered out of the page's DOM",
                  ascii_only(r["missing"])[-160:])
            return
        check(not r.get("errors"), "nothing in the page threw while it was driven",
              ascii_only(json.dumps(r.get("errors"))))
        print(f"  note  {exe.name}, {r.get('renderer','?')}, "
              f"canvas {r.get('canvas')}, {sum(r.get('ms', {}).values())} ms of "
              f"virtual time")

        # ---- it opened at all --------------------------------------------- #
        check(r.get("booted"), "the page opened, drew, and took the overlay down")
        check(r.get("gl") and r.get("decompression"),
              "a real WebGL2 context and a DecompressionStream",
              ascii_only(r.get("renderer", "")))
        check(r.get("err") == ["", "", ""],
              "a healthy page shows no damage message and hides nothing",
              ascii_only(json.dumps(r.get("err"))))
        cw, ch, bw, bh = r["canvas"]
        check((bw, bh) == (round(cw * r["dpr"]), round(ch * r["dpr"])),
              "the drawing buffer is the canvas at the device's pixel ratio",
              f"{cw}x{ch} css, {bw}x{bh} buffer, dpr {r['dpr']}")

        # ---- the counter over the view ------------------------------------ #
        pct = r.get("pct", [])
        nums = [int(p.split()[0]) for p in pct if p.split()[0].isdigit()]
        check(len(pct) >= 2 and pct[0] == "20 %" and pct[-1] == "100 %",
              "the counter gives a fifth of the wait to the base64 and the "
              "rest to the inflating", " -> ".join(pct))
        check(len(nums) == len(pct) and all(b > a for a, b in zip(nums, nums[1:])),
              "and it is written only when the number changes, never twice over",
              " -> ".join(pct))

        # ---- the view in the address -------------------------------------- #
        d = r["debounce"]
        check(d["immediate"], "the address is not rewritten the instant the "
              "model moves")
        # Bounded either side rather than pinned: what is measured is the
        # moment a poll twenty milliseconds apart NOTICED the write, and the
        # page is doing other work in between. Four seconds would fail here,
        # and so would no wait at all.
        check(300 <= d["ms"] <= 800, "but 400 ms after it stopped",
              f"{d['ms']} ms of virtual time, polled every 20")
        check(d["history"] <= 2, "and by replacing the entry, not by pushing "
              "one: the back button stays where it was",
              f"history.length {d['history']}")
        check(abs(d["ratio"] - 2.718281828 ** (120 * .0012)) < 2e-3,
              "the wheel moves the distance by exp(deltaY*.0012)",
              f"120 notches gave {d['ratio']}, exp(.144) is 1.15492")

        # ---- the drag, the click and the threshold between them ----------- #
        o = r["orbit"]
        check(o["pre"] < 1e-4 and o["post"] > 5e-2,
              "a drag turns about the axes of the SCREEN: the turn is applied "
              "before the camera's own rotation, at .008 rad a pixel",
              f"pre-multiplied differs by {o['pre']}, post- by {o['post']}")
        c = r["click"]
        # In model units, and not to the last digit: the ray cast here is
        # cast from the camera the ADDRESS carries, which is the page's own
        # to six digits, and three pixels is only a quarter of a millimetre
        # at this zoom. Half a pixel out is a fifth of that, and well inside
        # what tells this apart from a pivot that did not move at all.
        gap = max(abs(a - b) for a, b in zip(c["pivot"], c["hit"]))
        check(gap < c["px"] * 1.5,
              "a click of three pixels is a click: the centre of the turn "
              "lands on the point under the cursor",
              f"pivot {c['pivot']}, the ray says {c['hit']}, {gap:.3f} mm "
              f"apart, one pixel being {c['px']} mm")
        check(c["afterDrag"] == c["pivot"],
              "and one of ten pixels is a drag, which leaves it where it was",
              json.dumps(c["afterDrag"]))

        # ---- the keys ------------------------------------------------------ #
        k = r["keys"]
        check(k["view3"], "the number keys choose the view of that place in "
              "the menu (3 is the front)")
        check(k["modifierIgnored"],
              "and a key held with ctrl, alt or meta is the browser's, not ours")
        check(k["edge"] == "off" and k["proj"] == "persp"
              and k["back"] == ["ortho", "on"],
              "E and P flip the edges and the projection, through the radios "
              "themselves", f"{k['edge']} / {k['proj']} / {k['back']}")
        check(k["measure"] == [True, True] and k["measureOff"] is False,
              "M turns measuring on and off, and the view says so")
        check(k["menuOpen"] and k["menuClosed"],
              "and Escape closes the view menu and its scrim")

        # ---- a named view --------------------------------------------------- #
        v = r["showView"]
        check(v["pivot"] == [0, 0, 0],
              "a named view puts the centre of the turn back in the middle",
              json.dumps(v["pivot"]))
        check(v["rot"], "and takes its orientation from VIEWS, in menu order")
        check(abs(v["dist"] - v["wantDist"]) < .01
              and abs(v["oh"] - v["wantOh"]) < .01,
              "and refits it to the canvas afterwards, oh in step",
              f"dist {v['dist']} against {v['wantDist']}, oh {v['oh']}")

        # ---- the theme ------------------------------------------------------ #
        t = r["theme"]
        check(t["lightClass"] == (not t["sysDark"]),
              "with the theme on System the page follows the system",
              f"prefers dark: {t['sysDark']}, light class: {t['lightClass']}")
        # The system's own choice decides which of the two the page starts
        # with, so what System must paint is asked of the system, not
        # written down: headless Chrome prefers light today.
        check(t["bgSystem"] == ([20, 23, 28] if t["sysDark"] else [238, 241, 245])
              and t["bgLight"] == [238, 241, 245]
              and t["bgDark"] == [20, 23, 28] and not t["darkClass"],
              "and Light and Dark paint the background the theme's own colour",
              f"system {t['bgSystem']}, light {t['bgLight']}, "
              f"dark {t['bgDark']}")
        check(t["edgeDarkOn"] > 50 and t["edgeLightInDark"] == 0,
              "the edges are drawn in the dark theme's own colour",
              f"{t['edgeDarkOn']} pixels of (8,10,13), "
              f"{t['edgeLightInDark']} of the light theme's")
        check(t["edgeLightOn"] > 50 and t["edgeDarkInLight"] == 0,
              "and in the light theme's, the other way round",
              f"{t['edgeLightOn']} pixels of (26,33,43), "
              f"{t['edgeDarkInLight']} of the dark theme's")
        check(t["edgeLightOff"] == 0,
              "and none of them is drawn with the edges switched off",
              f"{t['edgeLightOff']} pixels")

        # ---- the model is where the projection says it is ------------------- #
        p = r["pixels"]
        check(p["corner"] == [238, 241, 245],
              "a corner of the canvas is background, so the model is fitted "
              "inside it", json.dumps(p["corner"]))
        check(p.get("tri", -1) >= 0 and p["pixel"] != p["corner"]
              and p["dominant"][0] == p["dominant"][1],
              "and the pixel where a triangle is carries that triangle's own "
              "colour - MVP is P times MV, or nothing is drawn there",
              f"triangle {p.get('tri')} is {p.get('vertexColour')}, "
              f"the pixel is {p.get('pixel')}")
        check(p["reproject"] and max(abs(v) for v in p["reproject"]) < 1,
              "the point the ray found projects back onto the pixel it was "
              "asked about", json.dumps(p["reproject"]))
        h = r["hover"]
        check(p.get("other") and h["hoverPixel"][2] > h["hoverPixel"][0] + 60
              and h["hoverPixel"][2] > h["hoverPixel"][1] + 30,
              "the face under the cursor is drawn again in the highlight "
              "colour", f"face {h['face']} at {h.get('at')}: {h['hoverPixel']}")
        check(h.get("movedFaces") == [h["face"]] and h.get("moved", 0) > 0
              and len(p.get("faces", [])) > 2,
              "and ONLY that face: of the points the ray found on the model, "
              "the ones that changed are exactly the hovered face's",
              f"{h.get('moved')} of {p.get('grid')} points changed, on "
              f"face(s) {h.get('movedFaces')}; the grid saw faces "
              f"{p.get('faces')} and hovered the middle one")

        # ---- the centre of the turn, drawn over the canvas ------------------ #
        m = r["marker"]
        check(m["want"] and abs(m["left"] - m["want"][0]) < .01
              and abs(m["top"] - m["want"][1]) < .01,
              "the marker sits exactly where toScreen puts the pivot - one "
              "mapping from a model point to a pixel, not two",
              f"({m['left']}, {m['top']}) against {m['want']}")
        check(abs(m["left"] - m["middle"][0]) > 50,
              "and the view was panned first, so that is not simply the "
              "middle of the canvas",
              f"middle {m['middle']}, pan {m['pan']}")
        check(m["heldAtOnce"] and m["heldLater"] and not m["afterDrag"],
              "it is held up for the whole of a turn, however long, and let "
              "go of after it",
              f"at once {m['heldAtOnce']}, 700 ms in {m['heldLater']} (longer "
              f"than any fade the page asks for), 600 ms after the drag "
              f"{m['afterDrag']}")

        # ---- the axis triad -------------------------------------------------- #
        a = r["axes"]
        check(all(a["arms"][c] == a["want"][c] for c in "xyz"),
              "each axis arm is drawn from (44,44), 30 long, with y up the "
              "screen", json.dumps(a["arms"]))
        check(a["order"] == a["wantOrder"] and a["wantOrder"] != a["natural"],
              "and they are drawn back to front, the arm pointing away first",
              f"{a['order']} at depths {a['depth']}")

        # ---- a measurement ---------------------------------------------------- #
        ms = r["measure"]
        check(len(ms.get("spots", [])) == 2, "two points were placed on the model",
              json.dumps(ms.get("spots")))
        check(ms.get("afterOne") == [False, True],
              "one point alone is not a measurement, and is drawn as one point")
        check(ms.get("label") == ms.get("want") and ms.get("labelOn"),
              "two give the distance in millimetres and each leg signed, to "
              "three decimals", ascii_only(ms.get("label", "")).replace("\n", " | "))
        check(ms.get("tags") == ms.get("wantTags"),
              "the legs carry their own lengths", json.dumps(ms.get("tags")))
        check(ms.get("legs") == ["", "", "none"],
              "and a leg of no length is not drawn at all",
              json.dumps(ms.get("legs")))
        check(ms.get("lead") == "", "the reading is on a lead")
        check(ms.get("dragged") and ms["wantDragged"]
              and max(abs(x - y) for x, y in zip(ms["dragged"], ms["wantDragged"]))
              < .01,
              "dragged out of the view, the reading is clamped back inside it",
              f"{ms.get('dragged')} against {ms.get('wantDragged')}")
        check(ms.get("afterThird") == [False, "none"],
              "a third click starts a fresh measurement rather than adding to one")
        check(ms.get("beforeEscape") and ms.get("afterEscape") == [False, "none"],
              "and Escape clears what was measured")
        check(ms.get("ringDown") and ms.get("ringAtOnce")
              and ms.get("ringAfter") is False
              and float(ms.get("ringOpacity", 1)) < .5,
              "the ring a press puts up lets go after a click that only "
              "places a point: measuring moves no centre of rotation for it "
              "to stay up for",
              f"on at the press {ms.get('ringDown')}, still on at the click "
              f"{ms.get('ringAtOnce')}, 500 ms later {ms.get('ringAfter')} "
              f"at opacity {ms.get('ringOpacity')}")
        tiny = (ms.get("tiny") or "").replace("\n", " | ")
        check(tiny.endswith("ΔZ 0.000") and "+0.000" not in tiny,
              "a leg below half of the last digit shown is printed as a plain "
              "nought, with no sign on it", ascii_only(tiny))
        rim = r["rim"]
        check(rim.get("points") == 49 and rim.get("rimShown") == "",
              "the rim under the cursor is drawn as 48 samples round the "
              "circle", f"{rim.get('points')} points of {rim.get('circle')}")
        check(rim.get("snapShown") == "" and rim.get("wantSnapAt")
              and max(abs(x - y) for x, y in zip(rim["snapAt"], rim["wantSnapAt"]))
              < .01,
              "and the ring that says what a click would take is on the "
              "circle's centre",
              f"{rim.get('snapAt')} against {rim.get('wantSnapAt')}")

        # ---- the picture that leaves ------------------------------------------ #
        g = r["png"]
        check(g.get("type") == "image/png" and g.get("bytes", 0) > 1000,
              "Save PNG hands over a PNG blob",
              f"{g.get('bytes')} bytes of {g.get('type')}")
        check(g.get("image") == g.get("canvas"),
              "the size of the canvas, in device pixels",
              f"{g.get('image')} against {g.get('canvas')}")
        check(g.get("name") == g.get("title"),
              "named after the page's own title", ascii_only(str(g.get("name"))))
        check(g.get("corner") and g["corner"][0] == g["corner"][1],
              "what it carries is what was on screen, pixel for pixel",
              json.dumps(g.get("corner")))
        check(g.get("markerOn") and g.get("crossOn")
              and min(g["crossOn"]) > 20,
              "with the centre of rotation drawn over it while it is showing",
              f"the four arms differ from the canvas by {g.get('crossOn')}")
        check(g.get("markerBefore") is False and g.get("crossOff") == [0, 0, 0, 0],
              "and without it in the picture taken before the click, when "
              "nothing was showing", json.dumps(g.get("crossOff")))
        check(g.get("stale") and g["stale"][0] != g["stale"][1]
              and g.get("afterStale") == g.get("wantStale"),
              "and it is drawn again before it is copied: with the canvas "
              "narrowed behind the page's back, the file still comes out the "
              "size the canvas is NOW",
              f"the buffer was {g.get('stale')} when the canvas had changed; "
              f"the file is {g.get('afterStale')}, the canvas "
              f"{g.get('wantStale')}")

        # ---- a camera moved by hand ------------------------------------------- #
        w = r["touched"]
        check(w["width"] != r["canvas"][:2],
              "the canvas really did change size", json.dumps(w["width"]))
        check(abs(w["keptAfterResize"][0] - w["keptAfterResize"][1]) < .01,
              "a camera the user has moved is not refitted when the window "
              "changes", f"{w['keptAfterResize'][0]} before, "
              f"{w['keptAfterResize'][1]} after")
        check(abs(w["home"][0] - w["home"][1]) < .01,
              "a double click fits the model to the canvas again",
              f"{w['home'][0]} against {w['home'][1]}")
        check(abs(w["refitted"][0] - w["refitted"][1]) < .01
              and abs(w["refitted"][0] - w["home"][0]) > .01,
              "and clears the mark, so the next resize refits it too",
              f"{w['refitted'][0]} against {w['refitted'][1]}")

        # ---- the address it was opened with ----------------------------------- #
        v = got["view"]
        check(v.get("hash") == VIEW,
              "a page opened at a #v= address restores that view, and keeps "
              "it against the fitting the first resize would do",
              ascii_only(str(v.get("hash"))))

        # ---- what the page refuses to draw ------------------------------------ #
        for name, what, words in (
                ("crc", "bytes that do not match the checksum beside them",
                 ("checksum", )),
                ("magic", "a payload that is not this tool's at all",
                 ("S3DH", )),
                ("version", "a payload in a format this page does not read",
                 ("format version 5", "version 4"))):
            d = got[name]
            text = d.get("text", "")
            check(d.get("err") == "grid" and d.get("canvas") == "none",
                  f"{what}: the message is shown and the canvas hidden",
                  f"err {d.get('err')}, canvas {d.get('canvas')}")
            check(all(w in text for w in words),
                  f"{what}: and it names the cause",
                  ascii_only(text)[:120])
        check("checksum" not in got["magic"]["text"]
              and "checksum" not in got["version"]["text"]
              and "damaged" not in got["magic"]["text"].lower()
              and "damaged" not in got["version"]["text"].lower(),
              "a whole file in the wrong format is not called a damaged one",
              ascii_only(got["magic"]["text"])[:80])

        # ---- and a browser with no WebGL --------------------------------------- #
        gl = got["nogl"]
        check(gl.get("err") == "grid" and gl.get("canvas") == "none"
              and "WebGL2" in gl.get("text", ""),
              "a browser without WebGL is told so, and nothing is drawn",
              ascii_only(gl.get("text", ""))[:90])

        # ---- a model with no edges in it --------------------------------------- #
        n = got["noedge"]
        check(n.get("edgeDisabled") == [True, True]
              and r["edgeDisabled"] == [False, False],
              "the edge radios are disabled for a model that has no edge "
              "lines, and live for one that has",
              f"no edges: {n.get('edgeDisabled')}, edges: {r['edgeDisabled']}")
        check(n.get("err") == "" and n.get("canvas") == "",
              "and such a model still opens and draws",
              f"err {n.get('err')}, canvas {n.get('canvas')}")

        # The profiles the browsers wrote, gone before the scratch folder
        # tries to remove itself: Windows keeps a handle on one of their
        # files for a moment after the process ends.
        for name in pages:
            shutil.rmtree(work / f"profile-{name}", ignore_errors=True)


if __name__ == "__main__":
    sys.exit(run(main, "the page in a browser"))
