// ==== png: what is on screen, into a file.
//
// Everything on screen, not just the triangles. The measurement, its
// stepped path, the numbers, the centre of rotation and the axis triad are
// DOM and SVG, and none of them is in the WebGL buffer - so they are drawn
// again onto a 2D canvas over it. Read back off the live elements rather
// than recomputed, so the file cannot disagree with what was on screen.
function paintSvgOnto(g, svg, offX, offY, k){
  for(const el of svg.children){
    if(el.style.display==='none') continue;
    const st=getComputedStyle(el);
    const dash=st.strokeDasharray;
    g.setLineDash(dash && dash!=='none'
      ? dash.split(/[ ,]+/).filter(Boolean).map(v=>parseFloat(v)*k) : []);
    if(el.tagName==='line'){
      g.strokeStyle=st.stroke;
      g.lineWidth=(parseFloat(st.strokeWidth)||1)*k;
      g.beginPath();
      g.moveTo((offX+ +el.getAttribute('x1'))*k, (offY+ +el.getAttribute('y1'))*k);
      g.lineTo((offX+ +el.getAttribute('x2'))*k, (offY+ +el.getAttribute('y2'))*k);
      g.stroke();
    } else if(el.tagName==='polyline'){
      // The caught rim. Stroked, never filled, whatever the ring encloses.
      const p=(el.getAttribute('points')||'').trim();
      if(!p) continue;
      g.strokeStyle=st.stroke;
      g.lineWidth=(parseFloat(st.strokeWidth)||1)*k;
      g.globalAlpha=parseFloat(st.opacity)||1;
      g.beginPath();
      p.split(/\s+/).forEach((pair,n)=>{
        const [px_,py_]=pair.split(',').map(Number);
        if(n) g.lineTo((offX+px_)*k,(offY+py_)*k);
        else  g.moveTo((offX+px_)*k,(offY+py_)*k);
      });
      g.stroke();
      g.globalAlpha=1;
    } else if(el.tagName==='circle'){
      // A ring if it is stroked and not filled, a dot if it is filled.
      const filled=st.fill && st.fill!=='none';
      g.setLineDash([]);
      g.beginPath();
      g.arc((offX+ +el.getAttribute('cx'))*k, (offY+ +el.getAttribute('cy'))*k,
            (+el.getAttribute('r'))*k, 0, 6.2832);
      if(filled){ g.fillStyle=st.fill; g.fill(); }
      else { g.strokeStyle=st.stroke;
             g.lineWidth=(parseFloat(st.strokeWidth)||1)*k; g.stroke(); }
    } else if(el.tagName==='text' && el.textContent){
      g.setLineDash([]);
      const size=(parseFloat(st.fontSize)||11)*k;
      g.font=`${st.fontWeight} ${size}px "Segoe UI",system-ui,sans-serif`;
      g.textAlign=(el.getAttribute('text-anchor')||st.textAnchor)==='middle'
                  ? 'center' : 'start';
      g.textBaseline=st.dominantBaseline==='middle' ? 'middle' : 'alphabetic';
      const x=(offX+ +el.getAttribute('x'))*k, y=(offY+ +el.getAttribute('y'))*k;
      // The halo the SVG gets from paint-order:stroke, so a number stays
      // readable over the model.
      if(parseFloat(st.strokeWidth)>1){
        g.lineWidth=parseFloat(st.strokeWidth)*k;
        g.strokeStyle=st.stroke; g.lineJoin='round';
        g.strokeText(el.textContent, x, y);
      }
      g.fillStyle=st.fill;
      g.fillText(el.textContent, x, y);
    }
  }
  g.setLineDash([]);
}
function roundRect(g,x,y,w,h,r){
  g.beginPath();
  g.moveTo(x+r,y); g.arcTo(x+w,y,x+w,y+h,r); g.arcTo(x+w,y+h,x,y+h,r);
  g.arcTo(x,y+h,x,y,r); g.arcTo(x,y,x+w,y,r); g.closePath();
}
// p carries the elements to copy - cv, marker, mline, axesSvg, mlabel - the
// title for the file name, and draw(), because the buffer is empty once
// composited and has to be drawn again to be read.
function savePng(p){
  p.draw();
  const cv=p.cv;
  const k=cv.width/Math.max(cv.clientWidth,1);
  const out=document.createElement('canvas');
  out.width=cv.width; out.height=cv.height;
  const g=out.getContext('2d');
  g.drawImage(cv,0,0);

  if(p.marker.classList.contains('on')){
    const x=(parseFloat(p.marker.style.left)||0)*k,
          y=(parseFloat(p.marker.style.top)||0)*k;
    g.strokeStyle=getComputedStyle(p.marker.querySelector('i')).borderTopColor;
    g.lineWidth=1.5*k;
    g.beginPath(); g.arc(x,y,7*k,0,6.2832); g.stroke();
    g.lineWidth=1*k;
    g.beginPath(); g.moveTo(x-13*k,y); g.lineTo(x+13*k,y);
                   g.moveTo(x,y-13*k); g.lineTo(x,y+13*k); g.stroke();
  }
  if(p.mline.classList.contains('on')) paintSvgOnto(g,p.mline,0,0,k);
  // Where the triad actually is, asked of the element rather than worked
  // out again from the stylesheet: a corner written down twice is a corner
  // that moves in one place and not the other. The offset is in CSS pixels
  // and the coordinates inside the SVG are user units, which are the same
  // thing only because #axes is 88 px wide with a 0 0 88 88 viewBox - keep
  // those two numbers equal or this needs a scale as well.
  const ar=p.axesSvg.getBoundingClientRect(), cr=cv.getBoundingClientRect();
  paintSvgOnto(g,p.axesSvg,ar.left-cr.left,ar.top-cr.top,k);
  if(p.mlabel.classList.contains('on')){
    const st=getComputedStyle(p.mlabel);
    const size=(parseFloat(st.fontSize)||12)*k;
    g.font=`${size}px "Segoe UI",system-ui,sans-serif`;
    const lines=p.mlabel.textContent.split('\n');
    const wide=Math.max(...lines.map(t=>g.measureText(t).width));
    const padX=8*k, padY=4*k, step=size*1.35;
    const bw=wide+padX*2, bh=step*lines.length+padY*2;
    const cx=(parseFloat(p.mlabel.style.left)||0)*k,
          cy=(parseFloat(p.mlabel.style.top)||0)*k;
    g.fillStyle=st.backgroundColor; g.strokeStyle=st.borderTopColor;
    g.lineWidth=1*k;
    roundRect(g,cx-bw/2,cy-bh/2,bw,bh,4*k); g.fill(); g.stroke();
    g.fillStyle=st.color; g.textAlign='center'; g.textBaseline='middle';
    lines.forEach((t,i)=>g.fillText(t,cx,cy-bh/2+padY+step*(i+.5)));
  }

  // A blob, not a data: URL. Chrome refuses to download a data: URL past
  // about two megabytes, and a full-screen shot of a board on a dense
  // display runs to several - which is why this quietly did nothing.
  out.toBlob(blob=>{
    if(!blob) return;
    const url=URL.createObjectURL(blob);
    const a=document.createElement('a');
    a.download=(p.title||'view')+'.png';
    a.href=url; a.click();
    setTimeout(()=>URL.revokeObjectURL(url),20000);
  },'image/png');
}
