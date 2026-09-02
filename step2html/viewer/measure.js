// ==== measure: two points, the line between them, the stepped path, and
// where the reading goes.
//
// A separate MODE, because a plain click already means "turn about this
// point" and one gesture cannot honestly mean two things. Drawn as an
// OVERLAY, not as geometry: two projected points and a line between them
// need no buffer, no draw call and no depth test, and a measurement should
// be readable through the model anyway.

// The caught rim, as a screen polyline. Sampled rather than drawn as an
// ellipse because a circle in perspective is only an ellipse when it is
// whole and unclipped, and this one is neither in general. project(p) is a
// model point to screen pixels, or null.
function rimPath(c,project){
  const n=c.n;
  const t=Math.abs(n[2])<.9?[0,0,1]:[1,0,0];
  let ux=n[1]*t[2]-n[2]*t[1], uy=n[2]*t[0]-n[0]*t[2], uz=n[0]*t[1]-n[1]*t[0];
  const m=Math.hypot(ux,uy,uz)||1; ux/=m; uy/=m; uz/=m;
  const vx=n[1]*uz-n[2]*uy, vy=n[2]*ux-n[0]*uz, vz=n[0]*uy-n[1]*ux;
  const out=[];
  for(let k=0;k<=48;k++){
    const a=k/48*6.283185307, ca=Math.cos(a)*c.r, sa=Math.sin(a)*c.r;
    const s=project([c.p[0]+ux*ca+vx*sa, c.p[1]+uy*ca+vy*sa,
                     c.p[2]+uz*ca+vz*sa]);
    if(!s) return '';
    out.push(s[0].toFixed(1)+','+s[1].toFixed(1));
  }
  return out.join(' ');
}

// One frame of the overlay. m carries everything it reads:
//   cv, mline, mlabel          the canvas, the SVG and the reading
//   marks, markCir             the points placed, and the circle each came from
//   measuring                  whether the mode is on
//   hoverPoint, cursor, snapNow   what the cursor is over right now
//   labelAt                    where the reading was dragged to, or null
//   project(p)                 a model point to screen pixels, or null
//   furniture                  the elements the reading must not cover
function paintMeasure(m){
  const cv=m.cv, mline=m.mline, mlabel=m.mlabel, marks=m.marks, project=m.project;
  // Asked for ONCE. This runs on every frame of a drag, and a
  // getBoundingClientRect after a style has been written forces the browser
  // to lay the page out again to answer it - three of them in here was two
  // too many, and one expression was asking twice on its own.
  const cr=cv.getBoundingClientRect();
  // With one point placed, the second end of the line is wherever the
  // cursor is: the point under it if there is one, and failing that the
  // cursor's own position on screen - with no number, because there is
  // nothing to measure to.
  const live = marks.length===1 && m.measuring
               ? (m.hoverPoint || null) : null;
  const ends = live ? [marks[0], live] : marks;
  const a=ends[0]&&project(ends[0]), b=ends[1]&&project(ends[1]);
  const loose = marks.length===1 && m.measuring && !live && m.cursor
                ? [m.cursor[0]-cr.left, m.cursor[1]-cr.top] : null;
  // The caught rim, shown whether or not a point has been placed: it is the
  // answer to "what will this click take", given before the click. The
  // other two belong to the points already placed, and stay up - so a
  // finished measurement, and the picture saved of it, says plainly that it
  // was taken centre to centre and not by eye.
  const rims=mline.querySelectorAll('polyline.rim'),
        rim=rims[0],
        snapC=mline.querySelector('circle.snap'),
        lead=mline.querySelector('line.lead');
  const sp=m.snapNow?project(m.snapNow.p):null;
  const path=m.snapNow?rimPath(m.snapNow,project):'';
  rim.setAttribute('points',path);
  rim.style.display=path?'':'none';
  for(let i=0;i<2;i++){
    const held=m.markCir[i] && i<marks.length ? rimPath(m.markCir[i],project) : '';
    rims[i+1].setAttribute('points',held);
    rims[i+1].style.display=held?'':'none';
  }
  if(sp){ snapC.setAttribute('cx',sp[0]); snapC.setAttribute('cy',sp[1]); }
  snapC.style.display=sp?'':'none';
  mline.classList.toggle('on', !!(a||sp));
  mlabel.classList.toggle('on', !!(a&&b));
  if(!b){
    mline.querySelectorAll('line.ax,text.ax')
         .forEach(e=>e.style.display='none');
    lead.style.display='none';
  }
  if(!a){
    mline.querySelectorAll('line.main,circle:not(.snap)')
         .forEach(el=>el.style.display='none');
    return;
  }
  const far = b || loose;
  // Named, not counted: the ring that marks a caught centre is a circle
  // too, and taking the first two of them by position would break the day
  // anything is added above these.
  const [c1,c2]=mline.querySelectorAll('circle:not(.snap)'),
        ln=mline.querySelector('line.main');
  c1.style.display='';
  c1.setAttribute('cx',a[0]); c1.setAttribute('cy',a[1]);
  c2.setAttribute('cx',(far||a)[0]); c2.setAttribute('cy',(far||a)[1]);
  c2.style.display=b?'':'none';
  ln.setAttribute('x1',a[0]); ln.setAttribute('y1',a[1]);
  ln.setAttribute('x2',(far||a)[0]); ln.setAttribute('y2',(far||a)[1]);
  ln.style.display=far?'':'none';
  if(!b) return;
  // Measured in MODEL space, so the number is millimetres and owes nothing
  // to the projection it happens to be looked at through.
  const dx=ends[1][0]-ends[0][0], dy=ends[1][1]-ends[0][1],
        dz=ends[1][2]-ends[0][2];
  // Each delta named and signed: "71.35" alone says neither which axis it
  // is on nor which way it points, and both matter when the question is
  // whether something clears something else.
  //
  // Thousandths, and the file can carry them: the coordinates are float32
  // about the middle of the model, so on a 160 mm board one step of the
  // format is some five millionths of a millimetre. What the third decimal
  // is WORTH is a different question, and it depends on where the point
  // came from - a centre snapped off a circle is exact, a point taken off a
  // surface is only as true as the mesh under it.
  const DP=3, ZERO=5e-4;      // below half of the last digit shown, say zero
  const g=(axis,v)=>{
    const n=Math.abs(v)<ZERO?0:v;
    return `Δ${axis} ${n>0?'+':''}${n.toFixed(DP)}`;
  };
  mlabel.textContent=`${Math.hypot(dx,dy,dz).toFixed(DP)} mm
`
                    +`${g('X',dx)}   ${g('Y',dy)}   ${g('Z',dz)}`;

  // The stepped path, the way a CAD viewer shows a distance in space: from
  // the first point along X, then along Y, then along Z to the second. Each
  // leg carries its own axis colour and its own number, and a leg of no
  // length is not drawn at all rather than drawn as a dot.
  const P=ends[0], Q=ends[1];
  const corners=[P, [Q[0],P[1],P[2]], [Q[0],Q[1],P[2]], Q].map(project);
  const legs=mline.querySelectorAll('line.ax'),
        tags=mline.querySelectorAll('text.ax');
  const deltas=[dx,dy,dz];
  for(let i=0;i<3;i++){
    const s0=corners[i], s1=corners[i+1];
    // A separate threshold from the one the numbers use, and a coarser one:
    // this asks whether a leg is long enough to SEE, not whether it is
    // large enough to print. A three-micron leg is a dot with a number on
    // top of it.
    const worth = s0 && s1 && Math.abs(deltas[i])>5e-3;
    legs[i].style.display = worth ? '' : 'none';
    tags[i].style.display = worth ? '' : 'none';
    if(!worth) continue;
    legs[i].setAttribute('x1',s0[0]); legs[i].setAttribute('y1',s0[1]);
    legs[i].setAttribute('x2',s1[0]); legs[i].setAttribute('y2',s1[1]);
    tags[i].setAttribute('x',(s0[0]+s1[0])/2);
    tags[i].setAttribute('y',(s0[1]+s1[1])/2-4);
    tags[i].setAttribute('text-anchor','middle');
    tags[i].textContent=Math.abs(deltas[i]).toFixed(DP);
  }

  // ---- where the reading goes --------------------------------------- #
  // Into the corner of the view furthest from the measurement, with a
  // thread back to the middle of the line. Sitting on that middle, which is
  // where it used to sit, it covered the very thing being measured.
  const W=cv.clientWidth, H=cv.clientHeight;
  const lw=mlabel.offsetWidth||150, lh=mlabel.offsetHeight||38;
  // Sampled ALONG the legs, not only at their ends: a corner far from every
  // end can still sit squarely on top of a long leg.
  const segs=[[a,b]];
  for(let i=0;i<3;i++)
    if(legs[i].style.display!=='none' && corners[i] && corners[i+1])
      segs.push([corners[i],corners[i+1]]);
  const pts=[];
  for(const s of segs)
    for(let k=0;k<=6;k++)
      pts.push([s[0][0]+(s[1][0]-s[0][0])*k/6,
                s[0][1]+(s[1][1]-s[0][1])*k/6]);
  // No corner is empty. The axis triad stands in one and the view cube in
  // another, and the help button - fixed to the top right of the WINDOW,
  // which in the side layout is over the canvas - stands in a third. Their
  // rectangles are ASKED OF THE ELEMENTS, not written down here as numbers:
  // the bottom two were numbers once, which is why the cube was cleared and
  // the help button, having no number of its own, was not.
  const M=12, GAP=8;
  const furniture=[];
  for(const el of m.furniture){
    const fb=el&&el.getBoundingClientRect();
    if(fb&&fb.width&&fb.height)
      furniture.push({l:fb.left-cr.left-GAP, t:fb.top-cr.top-GAP,
                      r:fb.right-cr.left+GAP, b:fb.bottom-cr.top+GAP});
  }
  // A corner is taken as given horizontally and pushed inwards vertically
  // until nothing is under the label any more.
  const clear=(cx_,cy_,inwards)=>{
    for(let pass=0;pass<4;pass++){
      let moved=false;
      for(const f of furniture){
        if(cx_+lw/2<f.l || cx_-lw/2>f.r) continue;
        if(cy_+lh/2<f.t || cy_-lh/2>f.b) continue;
        cy_ = inwards>0 ? f.b+lh/2 : f.t-lh/2;
        moved=true;
      }
      if(!moved) break;
    }
    return [cx_,cy_];
  };
  const cands=[clear(M+lw/2,   M+lh/2,     1), clear(W-M-lw/2, M+lh/2,     1),
               clear(M+lw/2, H-M-lh/2,    -1), clear(W-M-lw/2, H-M-lh/2,  -1)];
  let best=cands[0], bestD=-1;
  for(const c of cands){
    let d=1e9;
    for(const p of pts){
      const ox=Math.max(Math.abs(p[0]-c[0])-lw/2,0),
            oy=Math.max(Math.abs(p[1]-c[1])-lh/2,0);
      d=Math.min(d,Math.hypot(ox,oy));
    }
    if(d>bestD){ bestD=d; best=c; }
  }
  // Clamped into the view, so a window narrowed after the label was dragged
  // does not leave the reading somewhere off the edge. The dragged place
  // itself is kept as it was, and comes back when there is room again.
  const L=(m.labelAt||best).slice();
  L[0]=Math.max(lw/2+2, Math.min(W-lw/2-2, L[0]));
  L[1]=Math.max(lh/2+2, Math.min(H-lh/2-2, L[1]));
  mlabel.style.left=L[0]+'px';
  mlabel.style.top=L[1]+'px';
  // The thread starts at the label's own border rather than at its centre,
  // so it never crosses the text it comes from.
  const mx=(a[0]+b[0])/2, my=(a[1]+b[1])/2;
  const vx=mx-L[0], vy=my-L[1];
  const t=Math.min(lw/2/(Math.abs(vx)||1e-6), lh/2/(Math.abs(vy)||1e-6));
  const sx=L[0]+vx*t, sy=L[1]+vy*t;
  const worthLead=Math.hypot(mx-sx,my-sy)>8 && t<1;
  lead.style.display=worthLead?'':'none';
  if(worthLead){
    lead.setAttribute('x1',sx); lead.setAttribute('y1',sy);
    lead.setAttribute('x2',mx); lead.setAttribute('y2',my);
  }
}
