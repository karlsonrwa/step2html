// ==== pick: the point under the cursor, the face it is on, and the circle it is near.
//
// The depth buffer is not readable from the default framebuffer in WebGL,
// so the ray is cast against the triangles on the CPU. At a hundred and
// fifty thousand of them that is a few milliseconds, once per click, and it
// needs no second render target.
function pick(mesh,cam,MV,ortho,span,rect,clientX,clientY){
  const nx=2*(clientX-rect.left)/rect.width-1, ny=1-2*(clientY-rect.top)/rect.height;
  const t=Math.tan(FOV/2), a=Math.max(.2,rect.width/rect.height);
  // The orthographic ray starts on the view plane, and its half-height is
  // cam.oh - the same number the projection uses. Reading it off cam.dist
  // instead was a ray cast at the wrong scale, which picked the wrong
  // triangle and took the clipping planes with it.
  // The orthographic ray starts WELL IN FRONT of the model, not on the
  // camera plane. On the camera plane anything nearer to the viewer is
  // behind the ray's origin and is thrown away by the t>0 test - while
  // still being drawn, because the near clipping plane sits span*4 further
  // back. cam.dist shrinks both when the wheel is turned and when a click
  // puts the centre of rotation on a near surface, so that plane can end
  // up inside the model. Parallel rays hit the same thing wherever they
  // start, so moving the origin costs nothing.
  const ov = ortho ? [nx*cam.oh*a, ny*cam.oh, span*4] : [0,0,0];
  const dv = ortho ? [0,0,-1] : [nx*t*a, ny*t, -1];
  const o=toModel(cam,MV,ov,false), d=toModel(cam,MV,dv,true);
  const pos=mesh.pos, idx=mesh.idx, ni=mesh.ni;
  let best=Infinity, hit=null, tri=-1;
  for(let i=0;i<ni;i+=3){
    const ia=idx[i]*3, ib=idx[i+1]*3, ic=idx[i+2]*3;
    const e1x=pos[ib]-pos[ia], e1y=pos[ib+1]-pos[ia+1], e1z=pos[ib+2]-pos[ia+2];
    const e2x=pos[ic]-pos[ia], e2y=pos[ic+1]-pos[ia+1], e2z=pos[ic+2]-pos[ia+2];
    const px_=d[1]*e2z-d[2]*e2y, py_=d[2]*e2x-d[0]*e2z, pz_=d[0]*e2y-d[1]*e2x;
    const det=e1x*px_+e1y*py_+e1z*pz_;
    if(det>-1e-12 && det<1e-12) continue;
    const inv=1/det;
    const tx=o[0]-pos[ia], ty=o[1]-pos[ia+1], tz=o[2]-pos[ia+2];
    const u=(tx*px_+ty*py_+tz*pz_)*inv;
    if(u<0||u>1) continue;
    const qx=ty*e1z-tz*e1y, qy=tz*e1x-tx*e1z, qz=tx*e1y-ty*e1x;
    const v=(d[0]*qx+d[1]*qy+d[2]*qz)*inv;
    if(v<0||u+v>1) continue;
    const dist=(e2x*qx+e2y*qy+e2z*qz)*inv;
    if(dist>1e-6 && dist<best){best=dist; tri=i/3;
                               hit=[o[0]+d[0]*dist,
                                    o[1]+d[1]*dist,
                                    o[2]+d[2]*dist];}
  }
  return hit ? {hit,tri} : null;
}

// Which face a triangle belongs to: the starts are ascending, so this is a
// binary search and not a scan - it runs on every mouse move.
function faceOfTriangle(faceAt,nfa,tri){
  if(tri<0||!nfa) return -1;
  let lo=0, hi=nfa-1;
  while(lo<hi){ const mid=(lo+hi+1)>>1;
                if(faceAt[mid]<=tri) lo=mid; else hi=mid-1; }
  return lo;
}

// ---- snapping to a centre ------------------------------------------- #
// The circle is caught by its RIM, not by the wall of the hole: an arc has
// an exact centre, while a cylinder only gives an axis and the height along
// it would be wherever the cursor happened to be. The test is made against
// the VISIBLE point under the cursor, which is what keeps it from catching
// a hole on the far side of the board. tol is in model units - SNAP_PX
// pixels at the depth of the point, see pxSize.
const SNAP_PX=14;
function snapAt(cir,ncr,hit,tol){
  if(!ncr||!hit) return null;
  let bi=-1, bd=tol;
  for(let i=0;i<ncr;i++){
    const o=i*7;
    const dx=hit[0]-cir[o], dy=hit[1]-cir[o+1], dz=hit[2]-cir[o+2];
    const nx=cir[o+3], ny=cir[o+4], nz=cir[o+5];
    const h=dx*nx+dy*ny+dz*nz;
    if(Math.abs(h)>tol) continue;          // not in this circle's plane
    const ix=dx-nx*h, iy=dy-ny*h, iz=dz-nz*h;
    const off=Math.hypot(Math.hypot(ix,iy,iz)-cir[o+6],h);
    if(off<bd){ bd=off; bi=i; }
  }
  if(bi<0) return null;
  const o=bi*7;
  return {p:[cir[o],cir[o+1],cir[o+2]], n:[cir[o+3],cir[o+4],cir[o+5]],
          r:cir[o+6]};
}
