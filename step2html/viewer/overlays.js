// ==== overlays: the centre of rotation and the axis triad, DOM over the canvas.

// The centre of rotation, projected to a screen position once per frame -
// a great deal less than a second draw call - and CSS animates it for free.
function placeMarker(marker,MVP,pv,w,h){
  const pw=MVP[3]*pv[0]+MVP[7]*pv[1]+MVP[11]*pv[2]+MVP[15];
  if(pw>1e-6){
    const px_=(MVP[0]*pv[0]+MVP[4]*pv[1]+MVP[8]*pv[2]+MVP[12])/pw;
    const py_=(MVP[1]*pv[0]+MVP[5]*pv[1]+MVP[9]*pv[2]+MVP[13])/pw;
    marker.style.left=((px_*.5+.5)*w)+'px';
    marker.style.top=((.5-py_*.5)*h)+'px';
  }
}

// -> showMarker(fadeAfter): the marker shown with its pop restarted, and
// faded again after fadeAfter ms, or held up for 0.
function markerShower(marker){
  let timer=null;
  return function showMarker(fadeAfter){
    // Restarting a CSS animation needs the class off, a reflow, then on.
    marker.classList.remove('on');
    void marker.offsetWidth;
    marker.classList.add('on');
    clearTimeout(timer);
    if(fadeAfter) timer=setTimeout(()=>marker.classList.remove('on'),
                                   fadeAfter);
  };
}

// ---- which way is which -------------------------------------------- #
function paintAxes(axesSvg,rot){
  // Directions only, so this is the rotation and nothing else - no
  // projection, no distance, no pivot. Drawn back to front so the arm
  // pointing away from the viewer goes under the ones in front of it.
  const O=44, L=30;
  const arms=[0,1,2].map(i=>{
    const e=[0,0,0]; e[i]=1;
    return {i, x:rot[0]*e[0]+rot[4]*e[1]+rot[8]*e[2],
               y:rot[1]*e[0]+rot[5]*e[1]+rot[9]*e[2],
               z:rot[2]*e[0]+rot[6]*e[1]+rot[10]*e[2]};
  }).sort((p,q)=>p.z-q.z);
  for(const arm of arms){
    const cls=['x','y','z'][arm.i];
    const ln=axesSvg.querySelector('line.'+cls),
          tx=axesSvg.querySelector('text.'+cls);
    const ex=O+arm.x*L, ey=O-arm.y*L;          // y is up on screen
    ln.setAttribute('x1',O); ln.setAttribute('y1',O);
    ln.setAttribute('x2',ex); ln.setAttribute('y2',ey);
    tx.setAttribute('x',O+arm.x*(L+8)); tx.setAttribute('y',O-arm.y*(L+8));
    // Last drawn is on top, so re-appending in sorted order does the
    // depth sorting that SVG has no z-index for.
    axesSvg.appendChild(ln); axesSvg.appendChild(tx);
  }
}
