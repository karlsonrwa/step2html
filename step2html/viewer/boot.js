// ==== boot: the page put together.
//
// Everything with STATE lives here, in one function, declared at the top
// of it before anything that reads it; everything without state is in the
// files before this one and takes what it works on by argument. The files
// are concatenated into one script by page.py, in the order ORDER there
// names - a file:// page cannot load modules, so this is the one script
// there is.
const CRC=__CRC__, RAW=__RAW__;
const MSG={old:"__OLD_BROWSER__",gl:"__NO_WEBGL__",
           unpack:"__UNPACK_FAILED__",crc:"__CRC_FAILED__"};
const BG={dark:[.078,.090,.110],light:[.933,.945,.961]};
const EDGE_BIAS=__EDGE_BIAS__;
// Nothing here may throw. It once ended on a getElementById for an id that
// had been renamed away, which returns null: the message did appear, because
// that line came first, but the function died on the next one - so anything
// added after it would silently never have run, in the one function whose
// whole job is to keep the page's promise about a damaged file.
function fail(m){document.getElementById('errtext').textContent=m;
  document.getElementById('err').style.display='grid';
  document.getElementById('cv').style.display='none';
  document.getElementById('loading').style.display='none';}

async function boot(){
  // The counter over the view, up since the first paint: the base64 is a
  // fifth of the wait and the inflating the rest, and both report as they
  // go. Taken down just before the first frame, further down.
  const loading=document.getElementById('loading'),
        loadpct=document.getElementById('loadpct');
  let shown=-1;
  const tell=(phase,f)=>{
    const p=Math.round(phase==='decode' ? f*20 : 20+f*80);
    if(p!==shown){ shown=p; loadpct.textContent=p+' %'; }
  };
  let bin, crc;
  try{ ({bin,crc}=await inflate(document.getElementById('geo').textContent.trim(),RAW,tell)); }
  catch(e){ return fail(e&&e.kind==='old' ? MSG.old : MSG.unpack); }
  if(bin.length!==RAW||crc!==CRC)
    return fail(MSG.crc+' ('+RAW+' / '+CRC.toString(16)+')');
  const mesh=parsePayload(bin);
  const span=mesh.span, half=mesh.half, nfa=mesh.nfa, ncr=mesh.ncr,
        nei=mesh.nei, faceAt=mesh.faceAt, cir=mesh.cir;

  const cv=document.getElementById('cv');
  const gl=cv.getContext('webgl2',{antialias:true});
  if(!gl) return fail(MSG.gl);
  const renderer=createRenderer(gl,mesh,EDGE_BIAS);

  // ---- the elements --------------------------------------------------- #
  const marker=document.getElementById('pivot'), showMarker=markerShower(marker);
  const help=document.getElementById('help'), helpbox=document.getElementById('helpbox');
  const cube=document.getElementById('cube'), menu=document.getElementById('views'),
        scrim=document.getElementById('scrim');
  const measure=document.getElementById('measure'), mline=document.getElementById('mline'),
        mlabel=document.getElementById('mlabel'), view=document.getElementById('view');
  const axesSvg=document.getElementById('axes');
  const bar=document.getElementById('bar'), body=document.body;

  // ---- the state ------------------------------------------------------ #
  const home=()=>homeCam(cv.clientWidth,cv.clientHeight,half);
  let cam=home();
  let lastMV=null, lastP=null;     // the matrices of the last frame: picking and projecting use them
  // Orthographic and edges-on are the defaults; the theme follows the
  // system until a radio says otherwise, and goes on following it live.
  let ortho=true, edges=true, themeMode='system', light=false;
  let touched=false;               // the camera has been moved by hand: no more refitting on resize
  let hoverFace=-1, hoverPoint=null, hoverTri=-1, lastHover=0, cursor=null;
  // markCir runs alongside marks: the circle each placed point was taken
  // from, or null if it was taken off the surface itself.
  let marks=[], markCir=[], snapNow=null, labelAt=null;
  const ptrs=new Map();
  let pinch=null;
  const project=p=>(lastMV&&lastP)
      ? toScreen(lastMV,lastP,cv.clientWidth,cv.clientHeight,p) : null;

  // ---- one frame ------------------------------------------------------ #
  const overlay=()=>paintMeasure({cv,mline,mlabel,marks,markCir,
                                  measuring:measure.checked,hoverPoint,cursor,
                                  snapNow,labelAt,project,
                                  furniture:[help,cube,axesSvg]});
  function draw(){
    const w=cv.clientWidth,h=cv.clientHeight;
    const P=projection(cam,ortho,w/h,span), MV=modelView(cam);
    lastMV=MV; lastP=P;
    const MVP=renderer.draw(MV,P,{edges,light,hoverFace});
    placeMarker(marker,MVP,cam.pivot,w,h);
    overlay();
    paintAxes(axesSvg,cam.rot);
    rememberView();
  }

  // ---- the controls --------------------------------------------------- #
  const sysDark=matchMedia('(prefers-color-scheme: dark)');
  function applyTheme(){
    light = themeMode==='system' ? !sysDark.matches : themeMode==='light';
    document.documentElement.classList.toggle('light',light);
    renderer.clearColor(light?BG.light:BG.dark);
    draw();
  }
  const on=(name,fn)=>document.querySelectorAll('input[name='+name+']')
      .forEach(r=>r.addEventListener('change',e=>fn(e.target.value)));
  on('proj',  v=>{ortho=(v==='ortho'); draw();});
  on('edge',  v=>{edges=(v==='on');    draw();});
  on('theme', v=>{themeMode=v;         applyTheme();});
  if(sysDark.addEventListener)
    sysDark.addEventListener('change',()=>{if(themeMode==='system')applyTheme();});
  if(!nei) document.querySelectorAll('input[name=edge]')
      .forEach(r=>{r.disabled=true;});
  help.addEventListener('click',()=>helpbox.showModal());
  helpbox.querySelector('.close').addEventListener('click',()=>helpbox.close());
  document.getElementById('png').addEventListener('click',()=>savePng(
      {cv,marker,mline,axesSvg,mlabel,title:document.title,draw}));

  // ---- picking, for the turn and for the measurement ------------------ #
  function pickAt(clientX,clientY){
    if(!lastMV) return null;
    const got=pick(mesh,cam,lastMV,ortho,span,cv.getBoundingClientRect(),
                   clientX,clientY);
    hoverTri=got?got.tri:-1;
    return got?got.hit:null;
  }
  // What a click would take: the centre of the rim it has caught, if any.
  const snap=hit=>(hit&&lastMV)
      ? snapAt(cir,ncr,hit,SNAP_PX*pxSize(cam,lastMV,ortho,cv.clientHeight,hit))
      : null;

  // ---- the pointer ---------------------------------------------------- #
  // One pointer orbits (or pans with the right button / Shift), TWO pointers
  // pinch to zoom and drag to pan. A phone never sends a wheel event, so
  // without the two-pointer case there is no way to zoom on one at all.
  function twoFinger(){
    const [a,b]=[...ptrs.values()];
    const dx=b.x-a.x, dy=b.y-a.y;
    return {d:Math.hypot(dx,dy)||1, mx:(a.x+b.x)/2, my:(a.y+b.y)/2};
  }
  cv.addEventListener('pointerdown',e=>{
    cv.setPointerCapture(e.pointerId); touched=true;
    ptrs.set(e.pointerId,{x:e.clientX,y:e.clientY,
                          downX:e.clientX,downY:e.clientY,
                          pan:e.button===2||e.shiftKey});
    pinch = ptrs.size===2 ? twoFinger() : null;
    // Held up for the whole of a turn, so it is clear what is being turned
    // about, and not only for the instant of the click that set it.
    if(ptrs.size===1 && !(e.button===2||e.shiftKey)) showMarker(0);
  });
  function release(e){
    ptrs.delete(e.pointerId);
    // Back to one finger: forget the pinch, and the finger that stayed keeps
    // its last position, so the next move is a small delta, not a jump.
    pinch = ptrs.size===2 ? twoFinger() : null;
  }
  cv.addEventListener('pointerup',e=>{
    const p=ptrs.get(e.pointerId);
    // A click, not the end of a drag: a turn of four pixels is still a turn,
    // and moving the pivot underneath it would be a surprise.
    if(p && !p.pan && ptrs.size===1 && Math.hypot(e.clientX-p.downX,
                                                  e.clientY-p.downY) < 4){
      const raw=pickAt(e.clientX,e.clientY);
      // A click takes the centre it has caught, if it has caught one - and
      // only while measuring, because the centre of a hole is a poor place to
      // put the centre of the turn.
      const caught=measure.checked?snap(raw):null;
      const target=caught?caught.p:raw;
      if(measure.checked){
        // In measuring mode a click places a point and nothing else moves.
        // A third click starts a fresh measurement rather than adding to one.
        if(target){ if(marks.length>=2){ marks=[]; markCir=[]; labelAt=null; }
                    marks.push(target); markCir.push(caught); draw(); }
      }
      else if(target){ setPivot(cam,lastMV,target); draw(); showMarker(1200); }
      else showMarker(400);
    } else {
      showMarker(500);
    }
    release(e);
  });
  cv.addEventListener('pointercancel',release);
  cv.addEventListener('pointermove',e=>{
    // Hovering, which is what feeds the highlight and the line that follows
    // the cursor. Throttled by the clock rather than by an animation frame:
    // a frame callback never arrives in a view that is not being composited,
    // and this has to work there too.
    if(measure.checked && !ptrs.size){
      const now=performance.now();
      if(now-lastHover>16){
        lastHover=now;
        const raw=pickAt(e.clientX,e.clientY);
        hoverFace=faceOfTriangle(faceAt,nfa,raw?hoverTri:-1);
        snapNow=snap(raw);
        hoverPoint=snapNow?snapNow.p:raw;
        cursor=[e.clientX,e.clientY];
        draw();
      }
      return;
    }
    const p=ptrs.get(e.pointerId); if(!p) return;
    const ox=p.x, oy=p.y; p.x=e.clientX; p.y=e.clientY;
    if(ptrs.size>=2){
      const g=twoFinger();
      if(pinch){
        setDist(cam,span,cam.dist*pinch.d/g.d);
        cam.px+=(g.mx-pinch.mx)*cam.dist/900;
        cam.py-=(g.my-pinch.my)*cam.dist/900;
      }
      pinch=g; draw(); return;
    }
    const dx=e.clientX-ox, dy=e.clientY-oy;
    if(p.pan){cam.px+=dx*cam.dist/900;cam.py-=dy*cam.dist/900}
    else{
      // Pre-multiplied, so the turn is about the axes of the SCREEN and not
      // about axes carried around by the model. No limit in either direction.
      cam.rot=orthonormalise(mul(mul(rotX(dy*.008),rotY(dx*.008)),cam.rot));
    }
    draw();
  });
  cv.addEventListener('wheel',e=>{e.preventDefault();touched=true;
    setDist(cam,span,cam.dist*Math.exp(e.deltaY*.0012)); draw()},{passive:false});
  cv.addEventListener('contextmenu',e=>e.preventDefault());
  cv.addEventListener('pointerleave',()=>{
    if(hoverFace<0 && !cursor && !snapNow) return;
    hoverFace=-1; hoverPoint=null; cursor=null; snapNow=null; draw();
  });
  // Refit on resize, but only until the user has moved the camera themselves.
  cv.addEventListener('dblclick',()=>{touched=false;cam=home();draw()});

  // ---- the view cube -------------------------------------------------- #
  function closeMenu(){
    menu.classList.remove('open');
    scrim.classList.remove('open');
  }
  cube.addEventListener('click',e=>{
    e.stopPropagation();
    const open=menu.classList.toggle('open');
    scrim.classList.toggle('open',open);
  });
  // A click anywhere else lands on the scrim, which closes the menu and goes
  // no further - the requirement is that the view does NOT change, and the
  // canvas underneath would otherwise take the same click as a turn or as a
  // new centre of rotation.
  scrim.addEventListener('pointerdown',e=>{e.stopPropagation();closeMenu();});
  // One named view, set up once: the menu and the number keys both come here,
  // so the two cannot drift into meaning different things.
  function showView(i){
    cam=home();                       // pivot back to the middle, and refit
    cam.rot=new Float32Array(VIEWS[i]);
    cam.dist=fitDist(cam.rot,Math.max(.2,cv.clientWidth/cv.clientHeight),half);
    cam.oh=cam.dist*Math.tan(FOV/2);
    touched=true;                     // a chosen view is not to be refitted away
    closeMenu(); draw();
  }
  menu.addEventListener('click',e=>{
    const item=e.target.closest('button[data-view]');
    if(item) showView(+item.dataset.view);
  });

  // ---- measuring ------------------------------------------------------ #
  measure.addEventListener('change',()=>{
    view.classList.toggle('measuring',measure.checked);
    marks=[]; markCir=[]; hoverFace=-1; hoverPoint=null; cursor=null;
    snapNow=null; labelAt=null; draw();
  });
  // Dragged where it is wanted, if the corner chosen for it is the wrong one.
  // It holds that place until the measurement is cleared or replaced.
  mlabel.addEventListener('pointerdown',e=>{
    if(!mlabel.classList.contains('on')) return;
    e.preventDefault(); e.stopPropagation();
    const r=cv.getBoundingClientRect();
    const gx=e.clientX-r.left-(parseFloat(mlabel.style.left)||0),
          gy=e.clientY-r.top-(parseFloat(mlabel.style.top)||0);
    mlabel.setPointerCapture(e.pointerId);
    const move=ev=>{
      const rr=cv.getBoundingClientRect();
      labelAt=[ev.clientX-rr.left-gx, ev.clientY-rr.top-gy];
      overlay();
    };
    const up=ev=>{
      try{ mlabel.releasePointerCapture(ev.pointerId); }catch(_e){}
      mlabel.removeEventListener('pointermove',move);
      mlabel.removeEventListener('pointerup',up);
      mlabel.removeEventListener('pointercancel',up);
    };
    mlabel.addEventListener('pointermove',move);
    mlabel.addEventListener('pointerup',up);
    mlabel.addEventListener('pointercancel',up);
  });

  // ---- the keys ------------------------------------------------------- #
  // One place for every key, Escape included: it closes the menu AND clears
  // the measurement, and two listeners for one key is how they drift.
  addEventListener('keydown',e=>{
    if(e.ctrlKey||e.altKey||e.metaKey) return;
    const n=parseInt(e.key,10);
    if(n>=1&&n<=VIEWS.length){ showView(n-1); return; }
    const k=e.key.toLowerCase();
    const flip=(name,value)=>{
      const radio=[...document.querySelectorAll('input[name='+name+']')]
          .find(r=>r.value===value);
      radio.checked=true;
      radio.dispatchEvent(new Event('change',{bubbles:true}));
    };
    if(k==='e') flip('edge', edges?'off':'on');
    else if(k==='p') flip('proj', ortho?'persp':'ortho');
    else if(k==='m'){ measure.checked=!measure.checked;
        measure.dispatchEvent(new Event('change',{bubbles:true})); }
    else if(e.key==='Escape'){ closeMenu(); marks=[]; markCir=[]; labelAt=null;
                               overlay(); }
  });

  // ---- the view in the address ---------------------------------------- #
  // The address always names the view on screen, so a link to it is a copy
  // away. replaceState, not pushState: turning a model should not fill the
  // back button with a hundred entries.
  let hashTimer=null;
  function rememberView(){
    clearTimeout(hashTimer);
    hashTimer=setTimeout(()=>{
      try{ history.replaceState(null,'',encodeView(cam)); }catch(_e){}
    },400);
  }
  const saved=decodeView(location.hash);
  if(saved){ Object.assign(cam,saved); touched=true; }

  // ---- the layout ----------------------------------------------------- #
  // Decided twice on purpose: once straight away, and once more in the next
  // animation frame. The immediate pass keeps the page correct even where
  // frames are not being produced at all - an embedded or offscreen view
  // never runs a requestAnimationFrame callback, and a layout that waited
  // for one would simply never happen. The second pass re-measures after the
  // browser has settled, which is what catches a measurement taken mid-flight
  // during a resize.
  const settle=()=>{chooseLayout(bar,body);if(!touched)cam=home();draw();};
  let pending=false;
  const relayout=()=>{
    settle();
    if(pending) return;
    pending=true;
    requestAnimationFrame(()=>{pending=false;settle();});
  };
  // Two ways in, on purpose. A window resize is what a rotation or a dragged
  // window actually is; the observer catches the rest, such as the visible
  // height changing under a phone's address bar without a resize event.
  //
  // The observer is KEPT IN A VARIABLE and referenced again below. Written as
  // new ResizeObserver(...).observe(x) it has no strong reference left, and
  // it stops firing whenever the collector decides to take it - which is what
  // this did at first, silently: the layout was chosen once at load and never
  // again, and every redraw that made it look alive was coming from somewhere
  // else.
  //
  // The BODY is what is watched, never the view: the view is what this
  // resizes, and an observer on it would answer its own change for ever.
  addEventListener('resize',relayout);
  const ro=new ResizeObserver(relayout);
  ro.observe(body);
  addEventListener('pagehide',()=>ro.disconnect());
  chooseLayout(bar,body);
  loading.style.display='none';      // the next thing on screen is the model
  applyTheme();                      // sets the clear colour and draws
}
boot();
