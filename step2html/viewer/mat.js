// ==== mat: 4x4 matrices, column-major in Float32Arrays, the way WebGL wants them.
function mul(a,b){const r=new Float32Array(16);
  for(let i=0;i<4;i++)for(let j=0;j<4;j++){let s=0;
    for(let k=0;k<4;k++)s+=a[k*4+j]*b[i*4+k];r[i*4+j]=s}return r}
const rotX=a=>{const c=Math.cos(a),s=Math.sin(a);
  return new Float32Array([1,0,0,0, 0,c,s,0, 0,-s,c,0, 0,0,0,1]);};
const rotY=a=>{const c=Math.cos(a),s=Math.sin(a);
  return new Float32Array([c,0,-s,0, 0,1,0,0, s,0,c,0, 0,0,0,1]);};
function orthonormalise(m){
  // A rotation multiplied by another a few thousand times in float32 stops
  // being quite a rotation, and the model starts to shear. Gram-Schmidt on
  // the three columns, once per drag, costs nothing and prevents it.
  const dot=(a,b)=>a[0]*b[0]+a[1]*b[1]+a[2]*b[2];
  const norm=v=>{const l=Math.hypot(v[0],v[1],v[2])||1;
                 return [v[0]/l,v[1]/l,v[2]/l];};
  let u=norm([m[0],m[1],m[2]]);
  let v=[m[4],m[5],m[6]];
  const k=dot(v,u);
  v=norm([v[0]-k*u[0], v[1]-k*u[1], v[2]-k*u[2]]);
  const w=[u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]];
  m[0]=u[0];m[1]=u[1];m[2]=u[2];
  m[4]=v[0];m[5]=v[1];m[6]=v[2];
  m[8]=w[0];m[9]=w[1];m[10]=w[2];
  return m;
}
// A view basis from the direction the camera sits in, in model coordinates,
// and which way is up. Building a rotation from a basis rather than from a
// pair of angles keeps every named view honest at once: no ordering to get
// wrong, and a view reads as what it is.
function basis(d, up){
  const n=v=>{const l=Math.hypot(v[0],v[1],v[2])||1;
              return [v[0]/l,v[1]/l,v[2]/l];};
  const cr=(a,b)=>[a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2],
                   a[0]*b[1]-a[1]*b[0]];
  const z=n(d), x=n(cr(up,z)), y=cr(z,x);
  // Rows of the matrix are the axes: it takes model coordinates to view.
  return new Float32Array([x[0],y[0],z[0],0,
                           x[1],y[1],z[1],0,
                           x[2],y[2],z[2],0,
                           0,0,0,1]);
}
