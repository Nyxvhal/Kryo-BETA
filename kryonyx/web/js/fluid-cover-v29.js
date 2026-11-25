/* Continuous artwork-coloured fluid field. Own renderer, not Apple code or assets.
   Scene lifecycle is independent of lyric timing; reduced motion is respected. */
'use strict';
const FluidCover24={
 canvas:null,gl:null,ctx:null,raf:0,time:0,last:0,stamp:0,colors:null,target:null,engine:'none',frames:0,
 vertex:'attribute vec2 a; void main(){gl_Position=vec4(a,0.,1.);}',
 fragment:`precision mediump float;
 uniform vec2 resolution; uniform float time; uniform vec3 palette[4]; uniform float contrast;
 float pool(vec2 p,vec2 c,vec2 s){vec2 d=(p-c)/s;return exp(-dot(d,d)*2.05);}
 void main(){
  vec2 p=gl_FragCoord.xy/resolution;p.y=1.-p.y;float t=time;
  // Two flowing domains deform each other: the colour regions change shape,
  // rather than merely rotating/translating a still image.
  vec2 a=vec2(sin(p.y*4.8+t*.41)+.42*cos(p.x*7.2-t*.27),cos(p.x*4.3-t*.36)+.38*sin(p.y*6.1+t*.31));
  vec2 q=p+.16*a+.055*vec2(sin(a.y*2.3+t*.29),cos(a.x*2.0-t*.24));
  vec2 c0=vec2(.20+.42*sin(t*.36+.4),.64+.37*cos(t*.29+.2));
  vec2 c1=vec2(.77+.39*cos(t*.31+.8),.38+.41*sin(t*.34+1.9));
  vec2 c2=vec2(.61+.42*sin(t*.27+3.2),.12+.36*cos(t*.38+1.4));
  vec2 c3=vec2(.34+.39*cos(t*.33+2.1),.68+.38*sin(t*.25+4.4));
  float w0=.04+pool(q,c0,vec2(.64+.09*sin(t*.31),.59));
  float w1=.04+pool(q,c1,vec2(.57,.63+.10*cos(t*.28)));
  float w2=.04+pool(q,c2,vec2(.65,.55+.08*sin(t*.37)));
  float w3=.04+pool(q,c3,vec2(.58+.10*cos(t*.24),.66));
  vec3 col=(palette[0]*w0+palette[1]*w1+palette[2]*w2+palette[3]*w3)/(w0+w1+w2+w3);
  float light=.50+.12*sin(q.x*3.9-q.y*2.7+t*.32)+.06*cos(q.y*5.2+t*.23);
  float ribbon=pow(.5+.5*sin(q.y*7.5+sin(q.x*5.+t*.22)*1.5-t*.25),2.);
  col=mix(vec3(.012),col*(light+.28*ribbon)*contrast,.96);
  // Keep light text readable without turning the artwork colours into black.
  float lum=dot(pow(max(col,vec3(0.)),vec3(2.2)),vec3(.2126,.7152,.0722));
  col*=min(1.,pow(.085/max(lum,.001),1./2.2));
  col*=1.-.10*length((p-.5)*vec2(1.,.8));
  gl_FragColor=vec4(col,1.);
 }`,
 init(){
  if(this.canvas)return;const host=$('coverFlow23');if(!host)return;
  host.querySelectorAll('i').forEach(n=>n.remove());this.canvas=el('canvas');this.canvas.id='fluidCanvas24';this.canvas.setAttribute('aria-hidden','true');host.prepend(this.canvas);this.setup();
  this.colors=this.parse(CoverPalette23.forCover(Player.current?.thumbnail));this.target=this.colors.slice();
  addEventListener('kryonyx:coverpalette',()=>{this.target=this.parse(CoverPalette23.forCover(Player.current?.thumbnail));this.sync();});
  document.addEventListener('visibilitychange',()=>this.sync());addEventListener('resize',debounce(()=>{this.resize();this.draw();},120));
  new MutationObserver(()=>this.sync()).observe($('now'),{attributes:true,attributeFilter:['class']});
  new MutationObserver(()=>this.sync()).observe($('mSettings'),{attributes:true,attributeFilter:['class']});
  this.motion=matchMedia('(prefers-reduced-motion: reduce)');this.motion.addEventListener('change',()=>this.sync());this.resize();this.sync();
 },
 parse(colors){
  const fallback=CoverPalette23.neutral,values=Array.from({length:4},(_,i)=>/^#[0-9a-f]{6}$/i.test(colors?.[i]||'')?colors[i]:fallback[i]);
  const mono=values.every(c=>{const a=c.slice(1).match(/../g).map(x=>parseInt(x,16));return Math.max(...a)-Math.min(...a)<18;});
  if(mono)return [.035,.035,.035,.34,.34,.34,.72,.72,.72,.17,.17,.17];
  return values.flatMap(c=>{const rgb=c.slice(1).match(/../g).map(x=>parseInt(x,16)/255),max=Math.max(...rgb),min=Math.min(...rgb);const gain=max-min>.08?Math.min(1.65,.78/Math.max(max,.01)):1.12;return rgb.map(v=>Math.min(.78,v*gain));});
 },
 setup(){
  try{
   const gl=this.canvas.getContext('webgl',{alpha:false,antialias:false,powerPreference:'low-power',preserveDrawingBuffer:false});if(!gl)throw Error('WebGL unavailable');
   const shader=(type,source)=>{const s=gl.createShader(type);gl.shaderSource(s,source);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(s));return s;};
   const program=gl.createProgram();gl.attachShader(program,shader(gl.VERTEX_SHADER,this.vertex));gl.attachShader(program,shader(gl.FRAGMENT_SHADER,this.fragment));gl.linkProgram(program);if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw Error('Fluid field linking failed');gl.useProgram(program);
   const buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,-1,1,1,-1,1,1]),gl.STATIC_DRAW);const a=gl.getAttribLocation(program,'a');gl.enableVertexAttribArray(a);gl.vertexAttribPointer(a,2,gl.FLOAT,false,0,0);
   this.uniforms={resolution:gl.getUniformLocation(program,'resolution'),time:gl.getUniformLocation(program,'time'),palette:gl.getUniformLocation(program,'palette[0]'),contrast:gl.getUniformLocation(program,'contrast')};this.gl=gl;this.engine='webgl';
   this.canvas.addEventListener('webglcontextlost',event=>{event.preventDefault();this.stop();this.fallback();this.resize();this.sync();},{once:true});
  }catch{this.fallback();}
 },
 fallback(){const next=el('canvas');next.id='fluidCanvas24';next.setAttribute('aria-hidden','true');this.canvas.replaceWith(next);this.canvas=next;this.gl=null;this.ctx=next.getContext('2d',{alpha:false});this.engine=this.ctx?'canvas2d':'none';},
 resize(){if(!this.canvas)return;const box=$('coverFlow23').getBoundingClientRect(),w=box.width||innerWidth,h=box.height||innerHeight,max=(this.gl?320:220)*(this.resolutionScale||1),scale=Math.min(1,max/Math.max(w,1),256/Math.max(h,1));this.canvas.width=Math.max(96,Math.round(w*scale));this.canvas.height=Math.max(96,Math.round(h*scale));if(this.gl)this.gl.viewport(0,0,this.canvas.width,this.canvas.height);},
 still(){return !!S.noAnim||(this.motion||matchMedia('(prefers-reduced-motion: reduce)')).matches;},
 visible(){return $('now')?.classList.contains('on')&&$('now').classList.contains('album-flow23')&&!document.hidden&&!document.querySelector('.modal.on');},
 sync(){
  if(!this.canvas)return;
  if(!this.visible()||this.still()||this.engine==='none'){this.stop();if(this.still())this.colors=this.target?.slice()||this.colors;this.draw();return;}
  if(!this.raf){this.last=0;this.stamp=0;this.raf=requestAnimationFrame(t=>this.frame(t));}
 },
 stop(){if(this.raf)cancelAnimationFrame(this.raf);this.raf=0;this.last=0;},
 frame(now){
  this.raf=0;if(!this.visible()||this.still()){this.last=0;return;}
  if(!this.last)this.last=now;
  const fps = (!Player.audio || Player.audio.paused || Player.audio.ended) ? 12 : (this.gl ? (Number(S.auroraFps30) || 20) : 16);
  if(now-this.stamp>=1000/fps){const gap=now-this.last,dt=Math.min(.5,gap/1000);this.last=now;this.stamp=now;
   // Preserve motion and layout while reducing only internal pixel work under load.
   this.lateFrames=gap>55?(this.lateFrames||0)+1:Math.max(0,(this.lateFrames||0)-1);
   if(this.lateFrames>=6&&(this.resolutionScale||1)>.5){this.resolutionScale=Math.max(.5,(this.resolutionScale||1)*.75);this.lateFrames=0;this.resize();}
   // Visual ambience does not depend on Karaoke.playing or whether lyrics exist.
   // Pause keeps a quieter, continuous drift; hidden/disabled scenes stop entirely.
   const speed=Player.audio&&!Player.audio.paused&&!Player.audio.ended?1:.45;this.time+=dt*speed;
   if(this.target&&this.colors)this.colors=this.colors.map((v,i)=>v+(this.target[i]-v)*(1-Math.exp(-dt*1.25)));this.draw();}
  this.raf=requestAnimationFrame(t=>this.frame(t));
 },
 draw(){
  if(!this.colors||!this.canvas)return;this.frames++;
  if(this.gl){const gl=this.gl;gl.uniform2f(this.uniforms.resolution,this.canvas.width,this.canvas.height);gl.uniform1f(this.uniforms.time,this.time);gl.uniform1f(this.uniforms.contrast,Math.max(.6,Math.min(1.6,Number(S.auroraContrast30)||1.15)));if(!this.paletteBuffer42)this.paletteBuffer42=new Float32Array(12);this.paletteBuffer42.set(this.colors);gl.uniform3fv(this.uniforms.palette,this.paletteBuffer42);gl.drawArrays(gl.TRIANGLES,0,6);return;}
  const c=this.ctx;if(!c)return;const w=this.canvas.width,h=this.canvas.height,t=this.time;c.fillStyle='#040404';c.fillRect(0,0,w,h);
  // Broad ellipses change shape, size and independent paths in software mode too.
  for(let i=0;i<7;i++){const n=i%4,x=(.5+.50*Math.sin(t*(.27+i*.015)+i*1.71))*w,y=(.5+.47*Math.cos(t*(.34-i*.013)+i*2.03))*h,r=(.48+.10*Math.sin(t*.31+i))*Math.max(w,h),sx=1+.28*Math.sin(t*.29+i),sy=1+.24*Math.cos(t*.26+i*1.3);c.save();c.translate(x,y);c.rotate(.30*Math.sin(t*.24+i));c.scale(sx,sy);const rgb=this.colors.slice(n*3,n*3+3).map(v=>Math.round(v*255*.55*(Number(S.auroraContrast30)||1.15))),g=c.createRadialGradient(0,0,0,0,0,r);g.addColorStop(0,`rgba(${rgb.join(',')},.88)`);g.addColorStop(.45,`rgba(${rgb.join(',')},.52)`);g.addColorStop(1,`rgba(${rgb.join(',')},0)`);c.fillStyle=g;c.fillRect(-w*4,-h*4,w*8,h*8);c.restore();}
 }
};
