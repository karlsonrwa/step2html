// ==== layout: the bar wherever it leaves the SQUAREST view behind.
//
// A strip across the top costs height, a strip down the side costs width,
// and which of those hurts depends on the shape of the window: on a phone
// held sideways a top bar makes an already wide view wider still. Both are
// measured for real rather than guessed from an orientation media query,
// because the thickness of the bar is whatever its contents and wrapping
// make it, and that is not knowable in advance.
const oblong=(w,h)=>{w=Math.max(w,1);h=Math.max(h,1);return Math.max(w/h,h/w);};
function chooseLayout(bar,body){
  const W=innerWidth, H=innerHeight;
  body.classList.remove('side');
  const top=bar.offsetHeight;
  body.classList.add('side');
  const side=bar.offsetWidth;
  body.classList.toggle('side', oblong(W-side,H) < oblong(W,H-top));
}
