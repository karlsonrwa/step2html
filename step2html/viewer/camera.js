// ==== camera: an orientation MATRIX, a distance, an orthographic half-height,
// a pan, and the point the model is turned about.
//
// Orientation is a MATRIX, turned by the axes of the screen, not a pair of
// yaw and pitch angles. Angles have poles: pitch has to be stopped just
// short of straight down, or crossing it flips the horizon and reverses
// what a sideways drag does. That stop is what a drag runs into. A matrix
// turned about the screen's own axes has nowhere to run into - the model
// rolls on for ever in whichever direction the mouse goes.
//
// Every function here takes the camera it works on; none of them keeps one.
const FOV=Math.PI/6;                       // 30 degrees vertical

// Distance that just fits the eight bbox corners at this orientation. A
// bounding-sphere fit leaves a long thin board swimming in empty frame -
// measured 1.38x too far away on the folded rigid-flex test board.
function fitDist(rot,aspect,half){
  const t=Math.tan(FOV/2);
  let d=0;
  for(const sx of[-1,1])for(const sy of[-1,1])for(const sz of[-1,1]){
    const X=sx*half[0],Y=sy*half[1],Z=sz*half[2];
    const x=rot[0]*X+rot[4]*Y+rot[8]*Z;
    const y=rot[1]*X+rot[5]*Y+rot[9]*Z;
    const z=rot[2]*X+rot[6]*Y+rot[10]*Z;
    d=Math.max(d, Math.abs(x)/(t*aspect)+z, Math.abs(y)/t+z);
  }
  return d*1.04;
}
const HOME_ROT=mul(rotX(.95),rotY(-.6));   // the view it opens at

// The named views, each as the direction the CAMERA sits in, in model
// coordinates, plus which way is up. Order matters: it is the order of the
// menu, and data-view indexes into it.
const VIEWS=[
  basis([0,0,1],  [0,1,0]),      // top
  basis([0,0,-1], [0,1,0]),      // bottom
  basis([0,-1,0], [0,0,1]),      // front
  basis([0,1,0],  [0,0,1]),      // back
  basis([-1,0,0], [0,0,1]),      // left
  basis([1,0,0],  [0,0,1]),      // right
  basis([1,-1,1], [0,0,1]),      // top isometric
  basis([1,-1,-1],[0,0,-1]),     // bottom isometric
];

// A camera at the home view, fitted to a canvas of w by h. ||1 on both
// sides: a canvas that has not been laid out yet reports 0, and 0/0 is NaN,
// which would put the camera nowhere and draw a blank first frame until the
// observer fires.
//
// oh is the half-height the ORTHOGRAPHIC view shows, and it is a separate
// number from the distance on purpose. Moving the centre of the turn onto
// a picked point changes the distance to it - which leaves a perspective
// image untouched, but would rescale an orthographic one, since there the
// distance IS the zoom. Kept apart, a click changes nothing on screen in
// either projection, and the wheel moves both together so the two stay in
// step.
function homeCam(w,h,half){
  const d=fitDist(HOME_ROT, Math.max(.2,(w||1)/(h||1)), half);
  return {pivot:[0,0,0], rot:new Float32Array(HOME_ROT), dist:d,
          oh:d*Math.tan(FOV/2), px:0, py:0};
}

// The projection. Both are driven by the SAME cam.dist, and the
// orthographic half-height is dist*tan(FOV/2) - the size the perspective
// view has at the centre of rotation. So flipping between them does not
// jump, and the wheel keeps zooming in either one.
function projection(cam,ortho,a,span){
  if(ortho){
    const t=cam.oh, r=t*a,
          // Generous, and deliberately so: the pivot may sit on the near
          // face of the model, and the far side must still be inside.
          zn=cam.dist-span*4, zf=cam.dist+span*4;   // zn may go negative: fine
    return new Float32Array([1/r,0,0,0, 0,1/t,0,0, 0,0,-2/(zf-zn),0,
                             0,0,-(zf+zn)/(zf-zn),1]);
  }
  const f=1/Math.tan(.5*FOV),
        zn=Math.max(span*.005,cam.dist-span*1.5), zf=cam.dist+span*1.5;
  return new Float32Array([f/a,0,0,0, 0,f,0,0, 0,0,(zf+zn)/(zn-zf),-1,
                           0,0,2*zf*zn/(zn-zf),0]);
}

// The camera's own matrix: the model shifted so that cam.pivot sits at the
// centre of the turn, turned, then moved back by the pan and the distance.
// A click puts the pivot on the point under the cursor, which is what makes
// a big board inspectable: rotation and zoom then work on the detail being
// looked at rather than on the middle of the whole thing.
function modelView(cam){
  const Tv=new Float32Array([1,0,0,0, 0,1,0,0, 0,0,1,0, cam.px,cam.py,-cam.dist,1]);
  const Tp=new Float32Array([1,0,0,0, 0,1,0,0, 0,0,1,0,
                             -cam.pivot[0],-cam.pivot[1],-cam.pivot[2],1]);
  return mul(Tv,mul(cam.rot,Tp));
}

function setDist(cam,span,v){
  const next=Math.max(span*.05,Math.min(span*20,v));
  cam.oh*=next/Math.max(cam.dist,1e-9);      // zoom moves both
  cam.dist=next;
}

function setPivot(cam,MV,p){
  // Move the centre of the turn WITHOUT moving the picture. The picked
  // point keeps the place on screen it already had, because the camera
  // translation is set to exactly where that point sits in view space -
  // and cam.dist becomes the true distance to it, so zoom closes on it too.
  const vx=MV[0]*p[0]+MV[4]*p[1]+MV[8]*p[2]+MV[12];
  const vy=MV[1]*p[0]+MV[5]*p[1]+MV[9]*p[2]+MV[13];
  const vz=MV[2]*p[0]+MV[6]*p[1]+MV[10]*p[2]+MV[14];
  cam.pivot=p; cam.px=vx; cam.py=vy; cam.dist=-vz;
}

// A view-space point or direction back to model space. MV is rigid, so its
// inverse rotation is the transpose: dot with each column of the upper-left
// 3x3.
function toModel(cam,MV,v,isDirection){
  const x=v[0]-(isDirection?0:cam.px),
        y=v[1]-(isDirection?0:cam.py),
        z=v[2]+(isDirection?0:cam.dist);
  const a=MV[0]*x+MV[1]*y+MV[2]*z,
        b=MV[4]*x+MV[5]*y+MV[6]*z,
        c=MV[8]*x+MV[9]*y+MV[10]*z;
  return isDirection ? [a,b,c]
                     : [a+cam.pivot[0], b+cam.pivot[1], c+cam.pivot[2]];
}

// A model point to screen pixels on a w by h canvas, or null behind the camera.
function toScreen(MV,P,w,h,p){
  const x=MV[0]*p[0]+MV[4]*p[1]+MV[8]*p[2]+MV[12];
  const y=MV[1]*p[0]+MV[5]*p[1]+MV[9]*p[2]+MV[13];
  const z=MV[2]*p[0]+MV[6]*p[1]+MV[10]*p[2]+MV[14];
  const cx=P[0]*x+P[4]*y+P[8]*z+P[12];
  const cy=P[1]*x+P[5]*y+P[9]*z+P[13];
  const cw=P[3]*x+P[7]*y+P[11]*z+P[15];
  if(cw<=1e-6) return null;
  return [(cx/cw*.5+.5)*w, (.5-cy/cw*.5)*h];
}

// Model units per screen pixel, at the depth of the point in question.
function pxSize(cam,MV,ortho,h,p){
  h=Math.max(1,h);
  if(ortho) return 2*cam.oh/h;
  const vz=MV[2]*p[0]+MV[6]*p[1]+MV[10]*p[2]+MV[14];
  return 2*Math.tan(FOV/2)*Math.max(1e-6,-vz)/h;
}
