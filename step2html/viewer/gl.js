// ==== gl: the two programs, their buffers, and one draw over them.
//
// The surfaces are lit in linear light from sRGB bytes and written back as
// sRGB; the edges are their own tiny program. Nothing here knows about the
// camera beyond the two matrices it is handed each frame.
function createRenderer(gl,mesh,edgeBias){
  const nv=mesh.nv, ni=mesh.ni, nei=mesh.nei, nfa=mesh.nfa, faceAt=mesh.faceAt;

  const vs=`#version 300 es
  in vec3 aP; in vec3 aN; in vec3 aC;
  uniform mat4 uMVP, uMV; uniform mat3 uNM;
  out vec3 vN, vC, vP;
  void main(){ vN=uNM*aN; vC=aC; vec4 p=uMV*vec4(aP,1.); vP=p.xyz;
    gl_Position=uMVP*vec4(aP,1.); }`;
  const fs=`#version 300 es
  precision highp float; in vec3 vN,vC,vP; out vec4 o;
  uniform float uHi;                       // 1 while the hovered face is drawn
  void main(){
    vec3 n=normalize(vN); if(!gl_FrontFacing) n=-n;
    vec3 v=normalize(-vP);
    vec3 base=pow(vC,vec3(2.2));            // the bytes are sRGB; light in linear
    float key=max(dot(n,normalize(vec3(.4,.5,1.))),0.);
    float fill=max(dot(n,normalize(vec3(-.6,-.3,.4))),0.)*.35;
    float head=max(dot(n,v),0.)*.35;
    float rim=pow(1.-max(dot(n,v),0.),3.)*.10;
    vec3 c=base*(.22+key*.85+fill+head)+rim;
    c=mix(c, vec3(.10,.42,.95)*(.30+key*.9+head), uHi);
    o=vec4(pow(clamp(c,0.,1.),vec3(1./2.2)),1.);}`;
  function sh(t,s){const x=gl.createShader(t);gl.shaderSource(x,s);gl.compileShader(x);
    if(!gl.getShaderParameter(x,gl.COMPILE_STATUS))throw gl.getShaderInfoLog(x);return x}
  const pr=gl.createProgram();
  gl.attachShader(pr,sh(gl.VERTEX_SHADER,vs));gl.attachShader(pr,sh(gl.FRAGMENT_SHADER,fs));
  gl.linkProgram(pr);gl.useProgram(pr);

  function buf(target,data,loc,size,type,norm){
    const b=gl.createBuffer();gl.bindBuffer(target,b);gl.bufferData(target,data,gl.STATIC_DRAW);
    if(loc>=0){gl.enableVertexAttribArray(loc);gl.vertexAttribPointer(loc,size,type,norm,0,0)}}
  const vaSurf=gl.createVertexArray(); gl.bindVertexArray(vaSurf);
  buf(gl.ARRAY_BUFFER,mesh.pos,gl.getAttribLocation(pr,'aP'),3,gl.FLOAT,false);
  const nf=new Float32Array(nv*3); for(let i=0;i<nv*3;i++) nf[i]=(mesh.nrmB[i]-128)/127;
  buf(gl.ARRAY_BUFFER,nf,gl.getAttribLocation(pr,'aN'),3,gl.FLOAT,false);
  buf(gl.ARRAY_BUFFER,mesh.colB,gl.getAttribLocation(pr,'aC'),3,gl.UNSIGNED_BYTE,true);
  buf(gl.ELEMENT_ARRAY_BUFFER,mesh.idx,-1,0,0,false);

  // Edges: their own tiny program and their own buffers.
  const epr=gl.createProgram();
  gl.attachShader(epr,sh(gl.VERTEX_SHADER,`#version 300 es
    in vec3 aP; uniform mat4 uMV, uP; uniform float uBias;
    void main(){ vec4 p=uP*uMV*vec4(aP,1.);
      // A line and the triangle edge under it now share their vertices, so
      // there is no geometric gap left to cover and this bias is NOT sized
      // to the model or to the mesh. All it answers is that a line and a
      // triangle are rasterised by different machinery and can disagree by
      // a quantum or two of the depth buffer. Hence a fixed slice of clip
      // depth: 1e-5 of the range is some eighty steps of a 24-bit buffer,
      // far too little to lift a line off the surface it lies on.
      p.z-=uBias*p.w; gl_Position=p; }`));
  gl.attachShader(epr,sh(gl.FRAGMENT_SHADER,`#version 300 es
    precision highp float; uniform vec3 uCol; out vec4 o;
    void main(){ o=vec4(uCol,1.); }`));
  gl.linkProgram(epr);
  const uEMV=gl.getUniformLocation(epr,'uMV'), uEP=gl.getUniformLocation(epr,'uP'),
        uECol=gl.getUniformLocation(epr,'uCol'), uEBias=gl.getUniformLocation(epr,'uBias');
  const vaEdge=gl.createVertexArray(); gl.bindVertexArray(vaEdge);
  gl.useProgram(epr);
  buf(gl.ARRAY_BUFFER,mesh.epos,gl.getAttribLocation(epr,'aP'),3,gl.FLOAT,false);
  buf(gl.ELEMENT_ARRAY_BUFFER,mesh.eidx,-1,0,0,false);
  gl.bindVertexArray(null);

  gl.enable(gl.DEPTH_TEST);          // clear colour comes from the theme
  // NOTHING is done to the fills. Polygon offset was tried on them twice and
  // is wrong both ways round. With a slope factor it multiplies the maximum
  // depth slope of the polygon, which runs away for a face standing edge-on
  // to the camera - a cylinder's silhouette, an oblique end cap - pushing it
  // behind the far wall of its own solid, so a capacitor rendered as an open
  // tube. Without the slope factor a constant nudge is far too small on
  // exactly those steep faces, and the edge lines break into dashes along
  // the rim of a board seen nearly edge-on. The bias belongs on the lines.
  const uMVP=gl.getUniformLocation(pr,'uMVP'),uMV=gl.getUniformLocation(pr,'uMV'),
        uNM=gl.getUniformLocation(pr,'uNM'),uHi=gl.getUniformLocation(pr,'uHi');

  return {
    clearColor(c){ gl.clearColor(c[0],c[1],c[2],1); },
    // One frame: the surfaces, the hovered face over itself, then the lines.
    // o is {edges, light, hoverFace}. -> the MVP, for placing overlays.
    draw(MV,P,o){
      const cv=gl.canvas;
      const w=cv.clientWidth,h=cv.clientHeight,dpr=Math.min(devicePixelRatio||1,2);
      // Only when it has actually changed. Assigning width or height reallocates
      // the drawing buffer even when the number is the same, and this runs on
      // every frame of every drag.
      const bw=Math.round(w*dpr), bh=Math.round(h*dpr);
      if(cv.width!==bw||cv.height!==bh){ cv.width=bw; cv.height=bh; }
      gl.viewport(0,0,cv.width,cv.height);
      gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
      const MVP=mul(P,MV);
      gl.useProgram(pr); gl.bindVertexArray(vaSurf);
      gl.uniformMatrix4fv(uMV,false,MV);
      gl.uniformMatrix4fv(uMVP,false,MVP);
      gl.uniformMatrix3fv(uNM,false,new Float32Array([MV[0],MV[1],MV[2],MV[4],MV[5],MV[6],MV[8],MV[9],MV[10]]));
      gl.uniform1f(uHi,0);
      gl.drawElements(gl.TRIANGLES,ni,gl.UNSIGNED_INT,0);
      // The hovered face, drawn a second time over itself in the highlight
      // colour. Its triangles are one contiguous run, so this is one extra
      // draw call over a range - LEQUAL because it is exactly the same
      // geometry at exactly the same depth as what is already there.
      if(o.hoverFace>=0 && nfa){
        const from=faceAt[o.hoverFace]*3;
        const to=(o.hoverFace+1<nfa ? faceAt[o.hoverFace+1]*3 : ni);
        gl.depthFunc(gl.LEQUAL);
        gl.uniform1f(uHi,1);
        gl.drawElements(gl.TRIANGLES,to-from,gl.UNSIGNED_INT,from*4);
        gl.uniform1f(uHi,0);
        gl.depthFunc(gl.LESS);
      }
      if(o.edges&&nei){
        // LEQUAL as well: a line and the chords of the mesh that bounds it
        // are not at identical depth, and ties should go to the line.
        gl.depthFunc(gl.LEQUAL);
        gl.useProgram(epr); gl.bindVertexArray(vaEdge);
        gl.uniformMatrix4fv(uEMV,false,MV);
        gl.uniformMatrix4fv(uEP,false,P);
        gl.uniform3fv(uECol,o.light?[.10,.13,.17]:[.03,.04,.05]);
        gl.uniform1f(uEBias,edgeBias);
        gl.drawElements(gl.LINES,nei,gl.UNSIGNED_INT,0);
        gl.depthFunc(gl.LESS);
      }
      return MVP;
    }
  };
}
