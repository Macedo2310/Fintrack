
(() => {
  const canvas = document.getElementById('grainientLanding');
  if (!canvas) return;

  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const gl = canvas.getContext('webgl2', { alpha: true, antialias: false });
  if (!gl) {
    canvas.style.background = 'radial-gradient(circle at 65% 32%, #035439 0%, #033506 34%, #000 78%)';
    return;
  }

  const vertex = `#version 300 es
  in vec2 position;
  void main() {
    gl_Position = vec4(position, 0.0, 1.0);
  }`;

  // Fragment shader from the React Bits Grainient registry component.
  const fragment = `#version 300 es
  precision highp float;
  uniform vec2 iResolution;
  uniform float iTime;
  uniform float uTimeSpeed;
  uniform float uColorBalance;
  uniform float uWarpStrength;
  uniform float uWarpFrequency;
  uniform float uWarpSpeed;
  uniform float uWarpAmplitude;
  uniform float uBlendAngle;
  uniform float uBlendSoftness;
  uniform float uRotationAmount;
  uniform float uNoiseScale;
  uniform float uGrainAmount;
  uniform float uGrainScale;
  uniform float uGrainAnimated;
  uniform float uContrast;
  uniform float uGamma;
  uniform float uSaturation;
  uniform vec2 uCenterOffset;
  uniform float uZoom;
  uniform vec3 uColor1;
  uniform vec3 uColor2;
  uniform vec3 uColor3;
  uniform float uLightMode;
  out vec4 fragColor;

  #define S(a,b,t) smoothstep(a,b,t)
  mat2 Rot(float a){float s=sin(a),c=cos(a);return mat2(c,-s,s,c);}
  vec2 hash(vec2 p){p=vec2(dot(p,vec2(2127.1,81.17)),dot(p,vec2(1269.5,283.37)));return fract(sin(p)*43758.5453);}
  float noise(vec2 p){
    vec2 i=floor(p),f=fract(p),u=f*f*(3.0-2.0*f);
    float n=mix(
      mix(dot(-1.0+2.0*hash(i+vec2(0.0,0.0)),f-vec2(0.0,0.0)),
          dot(-1.0+2.0*hash(i+vec2(1.0,0.0)),f-vec2(1.0,0.0)),u.x),
      mix(dot(-1.0+2.0*hash(i+vec2(0.0,1.0)),f-vec2(0.0,1.0)),
          dot(-1.0+2.0*hash(i+vec2(1.0,1.0)),f-vec2(1.0,1.0)),u.x),u.y);
    return 0.5+0.5*n;
  }

  void mainImage(out vec4 o, vec2 C){
    float t=iTime*uTimeSpeed;
    vec2 uv=C/iResolution.xy;
    float ratio=iResolution.x/iResolution.y;
    vec2 tuv=uv-0.5+uCenterOffset;
    tuv/=max(uZoom,0.001);

    float degree=noise(vec2(t*0.1,tuv.x*tuv.y)*uNoiseScale);
    tuv.y*=1.0/ratio;
    tuv*=Rot(radians((degree-0.5)*uRotationAmount+180.0));
    tuv.y*=ratio;

    float frequency=uWarpFrequency;
    float ws=max(uWarpStrength,0.001);
    float amplitude=uWarpAmplitude/ws;
    float warpTime=t*uWarpSpeed;
    tuv.x+=sin(tuv.y*frequency+warpTime)/amplitude;
    tuv.y+=sin(tuv.x*(frequency*1.5)+warpTime)/(amplitude*0.5);

    vec3 colLav=uColor1;
    vec3 colOrg=uColor2;
    vec3 colDark=uColor3;
    float b=uColorBalance;
    float s=max(uBlendSoftness,0.0);
    mat2 blendRot=Rot(radians(uBlendAngle));
    float blendX=(tuv*blendRot).x;
    float edge0=-0.3-b-s;
    float edge1=0.2-b+s;
    float v0=0.5-b+s;
    float v1=-0.3-b-s;
    vec3 layer1=mix(colDark,colOrg,S(edge0,edge1,blendX));
    vec3 layer2=mix(colOrg,colLav,S(edge0,edge1,blendX));
    vec3 col=mix(layer1,layer2,S(v0,v1,tuv.y));

    vec2 grainUv=uv*max(uGrainScale,0.001);
    if(uGrainAnimated>0.5){grainUv+=vec2(iTime*0.05);}
    float grain=fract(sin(dot(grainUv,vec2(12.9898,78.233)))*43758.5453);
    col+=(grain-0.5)*uGrainAmount;

    col=(col-0.5)*uContrast+0.5;
    float luma=dot(col,vec3(0.2126,0.7152,0.0722));
    col=mix(vec3(luma),col,uSaturation);
    col=pow(max(col,0.0),vec3(1.0/max(uGamma,0.001)));
    col=clamp(col,0.0,1.0);

    if(uLightMode>0.5){
      float energy=max(max(col.r,col.g),col.b);
      vec3 hue=col/max(energy,0.001);
      float chroma=length(col-vec3(dot(col,vec3(0.333333))));
      float coverage=clamp(0.12+chroma*1.15+energy*0.18,0.0,0.88);
      col=mix(vec3(1.0),clamp(hue*0.58+col*0.18,0.0,1.0),coverage);
    }

    o=vec4(col,1.0);
  }

  void main(){
    vec4 o=vec4(0.0);
    mainImage(o,gl_FragCoord.xy);
    fragColor=o;
  }`;

  function compile(type, source) {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      console.error(gl.getShaderInfoLog(shader));
      gl.deleteShader(shader);
      return null;
    }
    return shader;
  }

  const vs = compile(gl.VERTEX_SHADER, vertex);
  const fs = compile(gl.FRAGMENT_SHADER, fragment);
  if (!vs || !fs) return;

  const program = gl.createProgram();
  gl.attachShader(program, vs);
  gl.attachShader(program, fs);
  gl.bindAttribLocation(program, 0, 'position');
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    console.error(gl.getProgramInfoLog(program));
    return;
  }

  const buffer = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 3,-1, -1,3]), gl.STATIC_DRAW);

  const vao = gl.createVertexArray();
  gl.bindVertexArray(vao);
  gl.enableVertexAttribArray(0);
  gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);

  const loc = name => gl.getUniformLocation(program, name);
  const U = {
    resolution:loc('iResolution'), time:loc('iTime'),
    timeSpeed:loc('uTimeSpeed'), colorBalance:loc('uColorBalance'),
    warpStrength:loc('uWarpStrength'), warpFrequency:loc('uWarpFrequency'),
    warpSpeed:loc('uWarpSpeed'), warpAmplitude:loc('uWarpAmplitude'),
    blendAngle:loc('uBlendAngle'), blendSoftness:loc('uBlendSoftness'),
    rotationAmount:loc('uRotationAmount'), noiseScale:loc('uNoiseScale'),
    grainAmount:loc('uGrainAmount'), grainScale:loc('uGrainScale'),
    grainAnimated:loc('uGrainAnimated'), contrast:loc('uContrast'),
    gamma:loc('uGamma'), saturation:loc('uSaturation'),
    center:loc('uCenterOffset'), zoom:loc('uZoom'),
    c1:loc('uColor1'), c2:loc('uColor2'), c3:loc('uColor3'),
    lightMode:loc('uLightMode')
  };

  const rgb = hex => {
    const n = parseInt(hex.slice(1),16);
    return [((n>>16)&255)/255,((n>>8)&255)/255,(n&255)/255];
  };

  // User-requested configuration.
  const config = {
    color1:'#000000',
    color2:'#033506',
    color3:'#035439',
    timeSpeed:0.25,
    colorBalance:0.0,
    warpStrength:1.0,
    warpFrequency:5.0,
    warpSpeed:2.0,
    warpAmplitude:50.0,
    blendAngle:0.0,
    blendSoftness:0.05,
    rotationAmount:500.0,
    noiseScale:2.0,
    grainAmount:0.1,
    grainScale:2.0,
    grainAnimated:false,
    contrast:1.5,
    gamma:1.0,
    saturation:1.0,
    centerX:0.0,
    centerY:0.0,
    zoom:0.9
  };

  gl.useProgram(program);
  gl.uniform1f(U.timeSpeed, config.timeSpeed);
  gl.uniform1f(U.colorBalance, config.colorBalance);
  gl.uniform1f(U.warpStrength, config.warpStrength);
  gl.uniform1f(U.warpFrequency, config.warpFrequency);
  gl.uniform1f(U.warpSpeed, config.warpSpeed);
  gl.uniform1f(U.warpAmplitude, config.warpAmplitude);
  gl.uniform1f(U.blendAngle, config.blendAngle);
  gl.uniform1f(U.blendSoftness, config.blendSoftness);
  gl.uniform1f(U.rotationAmount, config.rotationAmount);
  gl.uniform1f(U.noiseScale, config.noiseScale);
  gl.uniform1f(U.grainAmount, config.grainAmount);
  gl.uniform1f(U.grainScale, config.grainScale);
  gl.uniform1f(U.grainAnimated, config.grainAnimated ? 1 : 0);
  gl.uniform1f(U.contrast, config.contrast);
  gl.uniform1f(U.gamma, config.gamma);
  gl.uniform1f(U.saturation, config.saturation);
  gl.uniform2f(U.center, config.centerX, config.centerY);
  gl.uniform1f(U.zoom, config.zoom);
  gl.uniform3fv(U.c1, rgb(config.color1));
  gl.uniform3fv(U.c2, rgb(config.color2));
  gl.uniform3fv(U.c3, rgb(config.color3));
  gl.uniform1f(U.lightMode, 0);

  const resize = () => {
    const rect = canvas.getBoundingClientRect();
    const dpr = Math.min(devicePixelRatio || 1, 2);
    canvas.width = Math.max(1, Math.floor(rect.width*dpr));
    canvas.height = Math.max(1, Math.floor(rect.height*dpr));
    gl.viewport(0,0,canvas.width,canvas.height);
    gl.uniform2f(U.resolution, canvas.width, canvas.height);
  };
  resize();
  new ResizeObserver(resize).observe(canvas);

  const start = performance.now();
  let raf = 0;
  const render = now => {
    gl.uniform1f(U.time, reduced ? 0 : (now-start)*0.001);
    gl.drawArrays(gl.TRIANGLES,0,3);
    if (!reduced) raf=requestAnimationFrame(render);
  };

  if (reduced) render(start);
  else raf=requestAnimationFrame(render);

  document.addEventListener('visibilitychange', () => {
    if (document.hidden && raf) {
      cancelAnimationFrame(raf); raf=0;
    } else if (!document.hidden && !reduced && !raf) {
      raf=requestAnimationFrame(render);
    }
  });
})();
