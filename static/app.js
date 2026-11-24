
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const state={me:null,categories:null,txType:"",txPage:1,txPageSize:20,txDirty:false,currentConversation:null,amountAction:null,receiptId:null,currentPage:'dashboard',dashboardData:null,chartType:'line',chartRAF:0,chartHitAreas:[],chartReady:false};
const fmt=new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL"});
const money=c=>fmt.format((Number(c)||0)/100);
const brdate=s=>s?new Date(s+"T12:00:00").toLocaleDateString("pt-BR"):"—";
const uuid=()=>crypto.randomUUID?crypto.randomUUID():Date.now()+"-"+Math.random();
const esc=s=>String(s??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[m]));
function toast(msg,ok=true){const t=$("#toast");t.textContent=msg;t.style.borderColor=ok?"rgba(30,215,96,.45)":"rgba(255,116,116,.45)";t.classList.add("show");setTimeout(()=>t.classList.remove("show"),3200)}
/* ===== Avatar ===== */
function paintAvatar(el,av,uid){
  if(!el)return;
  if(!av){el.className="av preset";el.style.background="#1DB954";el.innerHTML='<img src="avatar-coruja.png" alt="">';return}
  if(av.kind==="photo"){
    el.className="av";el.style.background="#0c0c0c";
    const src=av.data_url||`/api/avatar/${encodeURIComponent(uid)}/photo?v=${encodeURIComponent(av.v||"")}`;
    el.innerHTML=`<img src="${src}" alt="">`;
  }else{
    el.className="av preset";el.style.background=av.bg||"#1DB954";
    el.innerHTML=`<img src="avatar-${encodeURIComponent(av.preset||"coruja")}.png" alt="">`;
  }
}
async function api(url,opt={}){
  const o={credentials:"same-origin",...opt}; if(o.body && !(o.body instanceof FormData)){o.headers={"Content-Type":"application/json",...(o.headers||{})};if(typeof o.body!=="string")o.body=JSON.stringify(o.body)}
  let r;try{r=await fetch(url,o)}catch{throw new Error("Sem conexão com o servidor. Verifique sua internet e tente novamente.")}
  let j={};try{j=await r.json()}catch{}
  if(r.status===401){location.href="/login.html?expired=1";throw new Error("Sua sessão expirou. Entre novamente.")}
  if(r.status===429)throw new Error(typeof j.detail==="string"?j.detail:"Muitas tentativas. Aguarde um pouco.");
  if(!r.ok)throw new Error(typeof j.detail==="string"?j.detail:"Não foi possível concluir a operação.");
  return j
}
/* Data de hoje no fuso de Brasília (UTC−3), igual à regra do servidor. */
function todayBR(){return new Date(Date.now()-3*3600e3).toISOString().slice(0,10)}
function monthStartBR(){return todayBR().slice(0,8)+"01"}
function modal(id,open=true){const m=$("#"+id);m.classList.toggle("open",open);m.setAttribute("aria-hidden",String(!open))}
$$("[data-close]").forEach(b=>b.addEventListener("click",()=>attemptClose(b.dataset.close)));
function attemptClose(id){if(id==="txModal"&&state.txDirty&&!confirm("Há alterações não salvas. Deseja descartá-las?"))return;modal(id,false);if(id==="txModal")state.txDirty=false}
function setPage(p){
  if(!document.getElementById("page-"+p))p="dashboard";
  history.replaceState(null,"","#"+p);
  document.dispatchEvent(new CustomEvent("fintrack:navigate",{detail:p}));
  state.currentPage=p;
  $$(".page").forEach(x=>x.classList.toggle("active",x.id==="page-"+p));
  $$(".nav button").forEach(x=>x.classList.toggle("active",x.dataset.page===p));
  const names={dashboard:"Dashboard",transactions:"Transações",goals:"Metas",education:"Educação",finbot:"IA financeira",classes:"Turmas",settings:"Configurações",notifications:"Lembretes"};
  $("#topTitle").textContent=names[p]||"FinTrack";
  if(p==="dashboard")loadDashboard();
  if(p==="transactions")loadTransactions();
  if(p==="goals")loadGoals();
  if(p==="education")loadEducation();
  if(p==="finbot")loadConversations();
  if(p==="classes")loadClasses();
  if(p==="settings")loadSettings();
  if(typeof updateMascotContext==="function") updateMascotContext(p);
}
$$(".nav button").forEach(b=>b.onclick=()=>setPage(b.dataset.page));

async function boot(){
  state.me=await api("/api/auth/me");if(!state.me.avatar){location.href="avatar.html";return}paintAvatar($("#sideAvatar"),state.me.avatar,state.me.id);$("#sideName").textContent=state.me.name;$("#sideRole").textContent=state.me.role==="professor"?"Professor":"Aluno";
  document.documentElement.dataset.theme=state.me.settings.theme||"dark";state.chartType=["line","bar","pie"].includes(state.me.settings.chart_type)?state.me.settings.chart_type:"line";initFinanceCharts();state.categories=await api("/api/categories");fillCategory(); if(typeof initMascot==="function") initMascot();
  $("#dashStart").value=monthStartBR();$("#dashEnd").value=todayBR();
  $("#txDate").value=todayBR();$("#recurrenceStart").value=$("#txDate").value;
  setPage(location.hash.slice(1)||"dashboard");checkDeploymentMode()
}
async function doLogout(){try{await api("/api/auth/logout",{method:"POST"})}catch{}sessionStorage.clear();location.replace("index.html")}
$("#logout").onclick=doLogout;
$("#logoutSettings")?.addEventListener("click",doLogout);

async function checkDeploymentMode(){
  try{
    const h=await api("/api/health");
    const box=$("#deploymentNotice");
    const notes=[];
    if(h.persistent===false)notes.push("Este servidor usa armazenamento temporário. Cadastros e dados podem desaparecer após reinícios.");
    if(h.email_ready===false)notes.push("O envio de resumo semanal por e-mail não está configurado neste servidor.");
    if(box&&notes.length){
      box.classList.remove("hidden");
      box.innerHTML="<b>Informações do ambiente</b><br>"+notes.map(esc).join("<br>");
    }
  }catch{}
}


const axisMoney=new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL",notation:"compact",maximumFractionDigits:1});
function chartCss(name,fallback){
  const v=getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v||fallback;
}
function chartColors(){
  return {
    text:chartCss("--text","#f6f6f6"),
    muted:chartCss("--muted","#9f9f9f"),
    line:chartCss("--line","#2a2a2a"),
    panel:chartCss("--panel","#111"),
    green:chartCss("--chart-in","#1ed760"),
    expense:chartCss("--chart-out","#ff8585")
  };
}
function prepareChartCanvas(){
  const canvas=$("#financeChart");
  if(!canvas)return null;
  const rect=canvas.getBoundingClientRect();
  if(rect.width<10||rect.height<10)return null;
  const dpr=Math.min(window.devicePixelRatio||1,2);
  const pxW=Math.max(1,Math.round(rect.width*dpr)),pxH=Math.max(1,Math.round(rect.height*dpr));
  if(canvas.width!==pxW||canvas.height!==pxH){canvas.width=pxW;canvas.height=pxH}
  const ctx=canvas.getContext("2d");
  ctx.setTransform(dpr,0,0,dpr,0,0);
  ctx.clearRect(0,0,rect.width,rect.height);
  return {canvas,ctx,w:rect.width,h:rect.height,dpr};
}
function setChartPicker(type){
  state.chartType=type;
  const body=$("#financeChartBody");if(body)body.dataset.chart=type;
  $$("#chartPicker [data-chart]").forEach(b=>{
    const on=b.dataset.chart===type;
    b.classList.toggle("active",on);
    b.setAttribute("aria-pressed",String(on));
  });
  const descriptions={
    line:"Acompanhe a evolução de receitas e despesas ao longo dos meses.",
    bar:"Compare receitas e despesas de cada mês lado a lado.",
    pie:"Veja como suas despesas do período estão distribuídas entre categorias."
  };
  const d=$("#financeChartDescription");if(d)d.textContent=descriptions[type]||descriptions.line;
  const canvas=$("#financeChart");if(canvas)canvas.setAttribute("aria-label",descriptions[type]||descriptions.line);
}
function financeChartHasData(data,type){
  if(!data)return false;
  if(type==="pie")return Array.isArray(data.categories)&&data.categories.some(x=>Number(x.amount_cents)>0);
  return Array.isArray(data.months)&&data.months.some(x=>Number(x.receitas)>0||Number(x.despesas)>0);
}
function updateChartLegend(data,type){
  const el=$("#financeChartLegend");if(!el)return;
  if(!financeChartHasData(data,type)){el.innerHTML="";return}
  if(type==="pie"){
    const total=data.categories.reduce((s,x)=>s+Number(x.amount_cents||0),0);
    const palette=["#1ed760","#10b981","#34d399","#8fc4ff","#b9a5ff","#ff9ec4","#ffd166","#ff8585","#5eead4"];
    el.innerHTML=data.categories.map((x,i)=>{
      const value=Number(x.amount_cents||0),pct=total?Math.round(value/total*100):0;
      return `<span class="chart-legend-item"><i class="chart-legend-dot" style="--legend-color:${palette[i%palette.length]}"></i><span>${esc(x.category)}</span><b>${pct}%</b></span>`;
    }).join("");
  }else{
    const income=data.months.reduce((s,x)=>s+Number(x.receitas||0),0);
    const expense=data.months.reduce((s,x)=>s+Number(x.despesas||0),0);
    el.innerHTML=`<span class="chart-legend-item"><i class="chart-legend-dot" style="--legend-color:#1ed760"></i><span>Receitas</span><b>${money(income)}</b></span><span class="chart-legend-item"><i class="chart-legend-dot" style="--legend-color:#ff8585"></i><span>Despesas</span><b>${money(expense)}</b></span>`;
  }
}
function drawChartGrid(ctx,w,h,pad,maxValue,colors){
  const plotW=w-pad.left-pad.right,plotH=h-pad.top-pad.bottom;
  ctx.save();
  ctx.font="10px Manrope, sans-serif";
  ctx.textBaseline="middle";
  ctx.lineWidth=1;
  for(let i=0;i<=4;i++){
    const y=pad.top+plotH*(i/4);
    ctx.strokeStyle=colors.line+"88";
    ctx.beginPath();ctx.moveTo(pad.left,y);ctx.lineTo(w-pad.right,y);ctx.stroke();
    const value=maxValue*(1-i/4);
    ctx.fillStyle=colors.muted;
    ctx.textAlign="right";
    ctx.fillText(axisMoney.format(value/100),pad.left-8,y);
  }
  ctx.restore();
}
function drawLineChart(env,data,progress){
  const {ctx,w,h}=env,colors=chartColors(),items=data.months;
  const pad={left:w<500?58:76,right:20,top:26,bottom:82};
  const largest=Math.max(1,...items.flatMap(x=>[Number(x.receitas||0),Number(x.despesas||0)]));
  const rawStep=largest*1.08/8,magnitude=10**Math.floor(Math.log10(rawStep));
  const step=Math.max(1,[1,2,2.5,5,10].find(n=>n*magnitude>=rawStep)*magnitude);
  const maxValue=Math.ceil(largest*1.08/step)*step,ticks=Math.round(maxValue/step);
  const formatAxis=value=>step<100?money(value):axisMoney.format(value/100);
  // Horizontal grid and plain axes, with evenly rounded currency ticks.
  ctx.save();ctx.font="12px Manrope, sans-serif";ctx.textAlign="right";ctx.textBaseline="middle";
  pad.left=Math.max(pad.left,...Array.from({length:ticks+1},(_,i)=>Math.ceil(ctx.measureText(formatAxis(step*i)).width)+16));
  const plotW=w-pad.left-pad.right,plotH=h-pad.top-pad.bottom,base=h-pad.bottom;
  for(let i=0;i<=ticks;i++){
    const y=base-plotH*i/ticks;
    ctx.globalAlpha=.3;ctx.strokeStyle=colors.muted;ctx.lineWidth=1;
    ctx.beginPath();ctx.moveTo(pad.left,y);ctx.lineTo(w-pad.right,y);ctx.stroke();
    ctx.globalAlpha=1;ctx.fillStyle=colors.muted;ctx.fillText(formatAxis(step*i),pad.left-10,y);
  }
  ctx.globalAlpha=.65;ctx.strokeStyle=colors.muted;ctx.lineWidth=1.25;
  ctx.beginPath();ctx.moveTo(pad.left,pad.top);ctx.lineTo(pad.left,base);ctx.lineTo(w-pad.right,base);ctx.stroke();
  ctx.restore();
  // Keep the end points inside the axes, as in a conventional line chart.
  const slotW=plotW/items.length;
  const xAt=i=>pad.left+slotW*(i+.5);
  const yAt=v=>pad.top+plotH-(Number(v||0)/maxValue)*plotH;
  const monthNames=["jan","fev","mar","abr","mai","jun","jul","ago","set","out","nov","dez"];
  ctx.save();ctx.font="12px Manrope, sans-serif";ctx.fillStyle=colors.text;
  items.forEach((x,i)=>{
    const px=xAt(i);
    ctx.strokeStyle=colors.muted;ctx.globalAlpha=.65;ctx.lineWidth=1;
    ctx.beginPath();ctx.moveTo(px,base);ctx.lineTo(px,base+6);ctx.stroke();
    const [year,month]=x.month.split("-");
    const label=`${monthNames[Number(month)-1]}/${year.slice(-2)}`;
    ctx.save();ctx.globalAlpha=1;ctx.translate(px,base+18);ctx.rotate(-Math.PI/4);
    ctx.textAlign="right";ctx.textBaseline="middle";ctx.fillText(label,0,0);ctx.restore();
  });
  ctx.restore();

  const reveal=pad.left+plotW*progress;
  const series=[{key:"receitas",color:colors.green},{key:"despesas",color:colors.expense}];
  series.forEach(s=>{
    ctx.save();
    ctx.beginPath();ctx.rect(pad.left-4,pad.top-8,Math.max(0,reveal-pad.left+8),plotH+16);ctx.clip();
    ctx.beginPath();
    if(items.length===1){
      const py=yAt(items[0][s.key]);
      ctx.arc(xAt(0),py,4,0,Math.PI*2);ctx.fillStyle=s.color;ctx.fill();
    }else{
      items.forEach((x,i)=>{const px=xAt(i),py=yAt(x[s.key]);if(i===0)ctx.moveTo(px,py);else ctx.lineTo(px,py)});
    }
    ctx.lineCap="round";ctx.lineJoin="round";ctx.globalAlpha=1;
    ctx.lineWidth=5;ctx.strokeStyle=s.color;ctx.stroke();
    ctx.restore();
  });

  state.chartHitAreas=items.map((x,i)=>{
    const center=xAt(i),prev=i?xAt(i-1):pad.left,next=i<items.length-1?xAt(i+1):w-pad.right;
    return {kind:"month",x1:i?(prev+center)/2:pad.left,x2:i<items.length-1?(center+next)/2:w-pad.right,y1:pad.top,y2:h-pad.bottom,label:x.month.split("-").reverse().join("/"),receitas:Number(x.receitas||0),despesas:Number(x.despesas||0)};
  });
}
function drawBarChart(env,data,progress){
  const {ctx,w,h}=env,colors=chartColors(),items=data.months;
  const pad={left:w<500?50:64,right:18,top:22,bottom:42};
  const plotW=w-pad.left-pad.right,plotH=h-pad.top-pad.bottom;
  const maxValue=Math.max(1,...items.flatMap(x=>[Number(x.receitas||0),Number(x.despesas||0)]))*1.12;
  drawChartGrid(ctx,w,h,pad,maxValue,colors);
  const groupW=plotW/items.length,barW=Math.max(5,Math.min(24,groupW*.28));
  ctx.save();ctx.font="10px Manrope, sans-serif";ctx.fillStyle=colors.muted;ctx.textAlign="center";ctx.textBaseline="top";
  state.chartHitAreas=[];
  items.forEach((x,i)=>{
    const cx=pad.left+groupW*(i+.5);
    const ih=(Number(x.receitas||0)/maxValue)*plotH*progress;
    const eh=(Number(x.despesas||0)/maxValue)*plotH*progress;
    const base=h-pad.bottom;
    ctx.fillStyle=colors.green;ctx.beginPath();roundRect(ctx,cx-barW-2,base-ih,barW,ih,4);ctx.fill();
    ctx.fillStyle=colors.expense;ctx.beginPath();roundRect(ctx,cx+2,base-eh,barW,eh,4);ctx.fill();
    ctx.fillStyle=colors.muted;
    const labelStep=Math.max(1,Math.ceil(items.length/Math.max(2,Math.floor(plotW/68))));
    if(i%labelStep===0||i===items.length-1)ctx.fillText(x.month.split("-").reverse().join("/"),cx,base+11);
    state.chartHitAreas.push({kind:"month",x1:pad.left+groupW*i,x2:pad.left+groupW*(i+1),y1:pad.top,y2:base,label:x.month.split("-").reverse().join("/"),receitas:Number(x.receitas||0),despesas:Number(x.despesas||0)});
  });
  ctx.restore();
}
function roundRect(ctx,x,y,w,h,r){
  if(h<=0||w<=0)return;
  r=Math.min(r,w/2,h/2);
  ctx.moveTo(x+r,y);ctx.arcTo(x+w,y,x+w,y+h,r);ctx.arcTo(x+w,y+h,x,y+h,r);ctx.arcTo(x,y+h,x,y,r);ctx.arcTo(x,y,x+w,y,r);ctx.closePath();
}
function drawPieChart(env,data,progress){
  const {ctx,w,h}=env,colors=chartColors();
  const items=data.categories.filter(x=>Number(x.amount_cents)>0);
  const total=items.reduce((s,x)=>s+Number(x.amount_cents||0),0);
  const palette=["#1ed760","#10b981","#34d399","#8fc4ff","#b9a5ff","#ff9ec4","#ffd166","#ff8585","#5eead4"];
  const cx=w*(w<600?.5:.43),cy=h*.49,r=Math.min(w,h)*(w<600?.30:.34),inner=r*.57;
  let start=-Math.PI/2;
  const totalSweep=Math.PI*2*progress;
  let used=0;state.chartHitAreas=[];
  items.forEach((x,i)=>{
    const full=(Number(x.amount_cents)/total)*Math.PI*2;
    const available=Math.max(0,Math.min(full,totalSweep-used));
    if(available<=0)return;
    const end=start+available;
    ctx.beginPath();ctx.arc(cx,cy,r,start,end);ctx.arc(cx,cy,inner,end,start,true);ctx.closePath();
    ctx.fillStyle=palette[i%palette.length];ctx.shadowColor=palette[i%palette.length]+"44";ctx.shadowBlur=12;ctx.fill();ctx.shadowBlur=0;
    if(progress>=.999)state.chartHitAreas.push({kind:"slice",cx,cy,r,inner,start,end:start+full,label:x.category,value:Number(x.amount_cents),color:palette[i%palette.length],total});
    start+=full;used+=full;
  });
  ctx.save();ctx.textAlign="center";ctx.textBaseline="middle";ctx.fillStyle=colors.text;ctx.font=`700 ${w<500?18:22}px Manrope, sans-serif`;ctx.fillText(money(total),cx,cy-4);ctx.fillStyle=colors.muted;ctx.font="10px Manrope, sans-serif";ctx.fillText("despesas no período",cx,cy+19);ctx.restore();
}
function renderFinanceChart(data=state.dashboardData,type=state.chartType,animate=true){
  state.dashboardData=data||state.dashboardData;
  const tip=$("#financeChartTooltip");if(tip){tip.classList.remove("show");tip.setAttribute("aria-hidden","true")}
  setChartPicker(type);
  updateChartLegend(state.dashboardData,type);
  const empty=$("#financeChartEmpty"),canvas=$("#financeChart");
  const has=financeChartHasData(state.dashboardData,type);
  $("#financeChartBody")?.classList.toggle("has-chart-data",has);
  if(empty)empty.classList.toggle("hidden",has);
  if(canvas)canvas.style.opacity=has?"1":"0";
  if(state.chartRAF){cancelAnimationFrame(state.chartRAF);state.chartRAF=0}
  state.chartHitAreas=[];
  if(!has)return;
  const reduced=matchMedia("(prefers-reduced-motion: reduce)").matches;
  const duration=(animate&&!reduced)?720:0,start=performance.now();
  const draw=now=>{
    const env=prepareChartCanvas();if(!env)return;
    const p=duration?Math.min(1,(now-start)/duration):1;
    const eased=1-Math.pow(1-p,3);
    if(type==="bar")drawBarChart(env,state.dashboardData,eased);
    else if(type==="pie")drawPieChart(env,state.dashboardData,eased);
    else drawLineChart(env,state.dashboardData,eased);
    if(p<1)state.chartRAF=requestAnimationFrame(draw);else state.chartRAF=0;
  };
  state.chartRAF=requestAnimationFrame(draw);
}
function hideFinanceTooltip(){
  const tip=$("#financeChartTooltip");
  if(tip){tip.classList.remove("show");tip.setAttribute("aria-hidden","true")}
}
function showFinanceTooltip(ev){
  const canvas=$("#financeChart"),tip=$("#financeChartTooltip");if(!canvas||!tip||!state.dashboardData)return;
  const rect=canvas.getBoundingClientRect(),x=ev.clientX-rect.left,y=ev.clientY-rect.top;
  let hit=null;
  if(state.chartType==="pie"){
    hit=state.chartHitAreas.find(a=>{
      const dx=x-a.cx,dy=y-a.cy,dist=Math.sqrt(dx*dx+dy*dy);
      if(dist<a.inner||dist>a.r)return false;
      let angle=Math.atan2(dy,dx);if(angle< -Math.PI/2)angle+=Math.PI*2;
      let s=a.start,e=a.end;if(e<s)e+=Math.PI*2;if(angle<s)angle+=Math.PI*2;
      return angle>=s&&angle<=e;
    });
    if(hit){
      const pct=Math.round(hit.value/hit.total*100);
      tip.innerHTML=`<b>${esc(hit.label)}</b>${money(hit.value)} • ${pct}%`;
    }
  }else{
    hit=state.chartHitAreas.find(a=>x>=a.x1&&x<=a.x2&&y>=a.y1&&y<=a.y2);
    if(hit)tip.innerHTML=`<b>${esc(hit.label)}</b><span style="color:#1ed760">Receitas: ${money(hit.receitas)}</span><br><span style="color:#ff8585">Despesas: ${money(hit.despesas)}</span>`;
  }
  if(!hit){tip.classList.remove("show");tip.setAttribute("aria-hidden","true");return}
  tip.classList.add("show");tip.setAttribute("aria-hidden","false");
  const tw=tip.offsetWidth||150,th=tip.offsetHeight||55;
  tip.style.left=Math.max(8,Math.min(rect.width-tw-8,x+14))+"px";
  tip.style.top=Math.max(8,Math.min(rect.height-th-8,y-th-12))+"px";
}
function initFinanceCharts(){
  if(state.chartReady)return;state.chartReady=true;
  document.fonts?.ready.then(()=>{if(state.dashboardData)renderFinanceChart(state.dashboardData,state.chartType,false)});
  const saved=state.me?.settings?.chart_type;
  setChartPicker(["line","bar","pie"].includes(saved)?saved:"line");
  $("#chartPicker")?.addEventListener("click",async e=>{
    const b=e.target.closest("[data-chart]");if(!b)return;
    const type=b.dataset.chart;if(type===state.chartType)return;
    setChartPicker(type);renderFinanceChart(state.dashboardData,type,true);
    try{
      const r=await api("/api/settings",{method:"PUT",body:{chart_type:type}});
      if(state.me)state.me.settings=r.settings;
    }catch(err){toast("O gráfico mudou, mas não foi possível salvar a preferência.",false)}
  });
  $("#financeChart")?.addEventListener("pointermove",showFinanceTooltip);
  $("#financeChart")?.addEventListener("pointerdown",showFinanceTooltip);
  $("#financeChart")?.addEventListener("pointerleave",e=>{if(e.pointerType!=="touch")hideFinanceTooltip()});
  $("#financeChart")?.addEventListener("pointercancel",hideFinanceTooltip);
  document.addEventListener("pointerdown",e=>{if(!$("#financeChartStage")?.contains(e.target))hideFinanceTooltip()});
  $("#chartEmptyAdd")?.addEventListener("click",()=>openTx());
  if("ResizeObserver" in window){
    new ResizeObserver(()=>{if(state.dashboardData)renderFinanceChart(state.dashboardData,state.chartType,false)}).observe($("#financeChartStage"));
  }else{
    addEventListener("resize",()=>{if(state.dashboardData)renderFinanceChart(state.dashboardData,state.chartType,false)},{passive:true});
  }
}

function simpleBars(el,items,labelKey,valueKey){
  if(!items.length){el.className="empty";el.innerHTML="<b>Sem dados suficientes</b>Adicione transações para construir este resumo.";return}
  el.className="";const max=Math.max(...items.map(x=>Number(x[valueKey])||0),1);
  el.innerHTML=items.map(x=>`<div style="display:grid;grid-template-columns:90px 1fr 90px;gap:8px;align-items:center;margin:9px 0"><span class="muted">${esc(x[labelKey])}</span><div class="progress"><i style="width:${Math.max(3,(Number(x[valueKey])||0)/max*100)}%"></i></div><b style="text-align:right">${money(x[valueKey])}</b></div>`).join("")
}

function maybeGoalAlert(goals){
  if(!state.me?.settings?.goal_alerts||sessionStorage.getItem("fintrack_goal_alert_shown")==="1")return;
  const now=new Date();now.setHours(0,0,0,0);
  const soon=(goals||[]).filter(g=>{
    if(g.status!=="ativa"||!g.deadline)return false;
    const d=new Date(g.deadline+"T12:00:00"),days=Math.ceil((d-now)/86400000);
    return days>=0&&days<=7;
  });
  if(soon.length){
    const g=soon[0],days=Math.ceil((new Date(g.deadline+"T12:00:00")-now)/86400000);
    toast(days===0?`A meta "${g.title}" vence hoje.`:`A meta "${g.title}" vence em ${days} dia(s).`);
    sessionStorage.setItem("fintrack_goal_alert_shown","1");
  }
}

async function loadDashboard(){
  try{
    const q=new URLSearchParams({start:$("#dashStart").value,end:$("#dashEnd").value});const d=await api("/api/dashboard?"+q);
    animMetrics(d);renderHighlights(d);
    state.dashboardData=d;
    renderFinanceChart(d,state.chartType,true);
    maybeGoalAlert(d.goals);syncAnalyzeButton();
    $("#recentList").innerHTML=d.recent.length?d.recent.map(x=>`<div class="tx-row"><span class="tx-ic ${x.type==="receita"?"in":"out"}">${esc((x.category||"?")[0]).toUpperCase()}</span><div class="tx-m"><b>${esc(x.description)}</b><small>${esc(x.category)} · ${brdate(x.date)}</small></div><b class="value ${x.type==="receita"?"in":"out"}">${x.type==="receita"?"+":"−"} ${money(x.amount_cents)}</b></div>`).join(""):`<div class="empty"><b>Nenhuma transação ainda</b><button class="btn primary" onclick="openTx()" style="margin-top:10px">Adicionar primeira transação</button></div>`;
    $("#dashGoals").innerHTML=d.goals.length?d.goals.map(g=>{const p=Math.min(100,Math.round((g.reserved_cents/g.target_cents)*100)||0);return`<div style="padding:9px 0"><div style="display:flex;justify-content:space-between"><b>${esc(g.title)}</b><span class="muted">${p}%</span></div><div class="progress" style="margin-top:7px"><i style="width:${p}%"></i></div></div>`}).join(""):`<div class="empty"><b>Nenhuma meta criada</b><button class="btn" onclick="setPage('goals')" style="margin-top:10px">Criar meta</button></div>`;
  }catch(e){toast(e.message,false)}
}
$("#dashApply").onclick=loadDashboard;

async function syncAnalyzeButton(){const b=$("#analyzeSpending");try{const s=await api("/api/ai/status");b.disabled=!s.configured;b.title=s.configured?"":"IA não configurada no servidor";if(!s.configured)$("#analysisBox").innerHTML='<div class="notice">A análise com IA está indisponível: nenhum provedor de IA foi configurado neste servidor. Seus dados não são enviados a nenhum serviço externo.</div>'}catch{}}
$("#analyzeSpending").onclick=async()=>{if(!confirm("Enviar ao provedor de IA configurado apenas os totais por categoria dos últimos 90 dias (sem descrições ou observações) para gerar a análise?"))return;
  const b=$("#analyzeSpending"),box=$("#analysisBox");b.disabled=true;b.textContent="Analisando...";
  try{const r=await api("/api/ai/analyze-spending",{method:"POST"});if(!r.has_data){box.innerHTML=`<div class="notice">${esc(r.message)} <button class="btn small" onclick="setPage('transactions')">Cadastrar transação</button></div>`}else box.innerHTML=`<div class="notice success"><b>Período:</b> ${brdate(r.period.start)} a ${brdate(r.period.end)}</div><div style="white-space:pre-wrap;margin-top:10px">${esc(r.analysis)}</div>`}catch(e){box.innerHTML=`<div class="notice error">${esc(e.message)}</div>`}finally{b.disabled=false;b.textContent="Analisar meus gastos"}
};

$("#txTypeTabs").onclick=e=>{const b=e.target.closest("button");if(!b)return;$$("#txTypeTabs button").forEach(x=>x.classList.toggle("active",x===b));fillCategory(b.dataset.value);state.txDirty=true};
function currentTxType(){return $("#txTypeTabs .active").dataset.value}
function fillCategory(type=currentTxType()){if(!state.categories)return;const current=$("#txCategory").value;const arr=[...state.categories[type],...state.categories.personalizadas.filter(x=>x.type===type).map(x=>x.name)];$("#txCategory").innerHTML='<option value="">Selecione</option>'+arr.map(x=>`<option>${esc(x)}</option>`).join("");if(arr.includes(current))$("#txCategory").value=current}
function openTx(tx=null){
  $("#txForm").reset();$("#txId").value="";$("#txModalTitle").textContent=tx?"Editar transação":"Nova transação";$("#txSubmit").textContent=tx?"Salvar alterações":"Adicionar transação";$("#txFormStatus").textContent="";
  $$(`#txTypeTabs button`).forEach(x=>x.classList.toggle("active",x.dataset.value===(tx?.type||"despesa")));fillCategory(tx?.type||"despesa");
  $("#txDate").value=tx?.date||todayBR();$("#recurrenceStart").value=$("#txDate").value;$("#recurrenceFields").classList.add("hidden");
  if(tx){$("#txId").value=tx.id;$("#txCategory").value=tx.category;$("#txValue").value=(tx.amount_cents/100).toFixed(2).replace(".",",");$("#txDescription").value=tx.description;$("#txNote").value=tx.note||""}
  state.txDirty=false;modal("txModal")
}

window.openTx=openTx;$("#newTxTop").onclick=()=>openTx();$("#newTxPage").onclick=()=>openTx();

$("#newCategoryBtn")?.addEventListener("click",()=>{
  const type=currentTxType();
  $("#categoryName").value="";
  $("#categoryStatus").textContent="";
  $("#categoryTypeNotice").textContent=`A categoria será criada para ${type==="receita"?"receitas":"despesas"}.`;
  modal("categoryModal");
  setTimeout(()=>$("#categoryName")?.focus(),60);
});
$("#saveCategoryBtn")?.addEventListener("click",async()=>{
  const name=$("#categoryName").value.trim(),type=currentTxType(),b=$("#saveCategoryBtn"),s=$("#categoryStatus");
  if(name.length<2){s.textContent="Digite um nome com pelo menos 2 caracteres.";return}
  b.disabled=true;s.textContent="";
  try{
    const r=await api("/api/categories",{method:"POST",body:{type,name}});
    state.categories=await api("/api/categories");
    fillCategory(type);
    $("#txCategory").value=r.name;
    modal("categoryModal",false);
    state.txDirty=true;
    toast("Categoria criada.");
  }catch(e){s.textContent=e.message}
  finally{b.disabled=false}
});

function updateRecurrencePreview(){const start=$("#recurrenceStart").value||$("#txDate").value,f=$("#recurrenceFrequency").value;if(!start){$("#recurrenceNext").value="—";return}const d=new Date(start+"T12:00:00");if(f==="semanal")d.setDate(d.getDate()+7);else if(f==="mensal"){const day=d.getDate();d.setDate(1);d.setMonth(d.getMonth()+1);const last=new Date(d.getFullYear(),d.getMonth()+1,0).getDate();d.setDate(Math.min(day,last))}else{const day=d.getDate(),m=d.getMonth();d.setFullYear(d.getFullYear()+1);if(d.getMonth()!==m)d.setDate(28);else d.setDate(day)}$("#recurrenceNext").value=d.toLocaleDateString("pt-BR")}
$("#txForm").addEventListener("input",()=>state.txDirty=true);$("#txRecurring").onchange=()=>{$("#recurrenceFields").classList.toggle("hidden",!$("#txRecurring").checked);updateRecurrencePreview()};$("#recurrenceFrequency").onchange=updateRecurrencePreview;$("#recurrenceStart").onchange=updateRecurrencePreview;$("#txDate").onchange=()=>{if(!$("#recurrenceStart").value)$("#recurrenceStart").value=$("#txDate").value;updateRecurrencePreview()};
$("#txForm").onsubmit=async e=>{
  e.preventDefault();const id=$("#txId").value,b=$("#txSubmit"),status=$("#txFormStatus");status.textContent="";
  const body={type:currentTxType(),category:$("#txCategory").value,description:$("#txDescription").value,amount:$("#txValue").value,date:$("#txDate").value,note:$("#txNote").value||null};
  if(!id && $("#txRecurring").checked)body.recurrence={enabled:true,frequency:$("#recurrenceFrequency").value,start_date:$("#recurrenceStart").value||$("#txDate").value,end_date:$("#recurrenceEnd").value||null};
  b.disabled=true;b.textContent="Salvando...";
  try{let url=id?"/api/transactions/"+id:"/api/transactions";if(id){const original=txCache.find(x=>x.id===id);if(original?.recurrence_id&&original.recurrence_active&&confirm("Esta transação é recorrente.\n\nOK: aplicar a alteração a esta e às próximas ocorrências.\nCancelar: alterar somente esta ocorrência."))url+="?scope=future"}await api(url,{method:id?"PUT":"POST",body});state.txDirty=false;modal("txModal",false);toast(id?"Transação atualizada.":"Transação adicionada.");loadTransactions();loadDashboard()}catch(err){status.textContent=err.message}finally{b.disabled=false;b.textContent=id?"Salvar alterações":"Adicionar transação"}
};
let txCache=[];
async function loadTransactions(){
  const q=new URLSearchParams({page:state.txPage,page_size:state.txPageSize,sort:$("#txSort").value});
  if(state.txType)q.set("type",state.txType);if($("#txStart").value)q.set("start",$("#txStart").value);if($("#txEnd").value)q.set("end",$("#txEnd").value);if($("#txSearch").value.trim())q.set("q",$("#txSearch").value.trim());
  try{
    const r=await api("/api/transactions?"+q);txCache=r.items;
    $("#txSummary").textContent=`Receitas ${money(r.summary.receitas)} • Despesas ${money(r.summary.despesas)} • Resultado ${money(r.summary.resultado)}`;
    const FREQ={semanal:"semanal",mensal:"mensal",anual:"anual"};
    $("#txBody").innerHTML=r.items.map(x=>`<tr><td data-label="Descrição">${esc(x.description)}${x.recurrence_id?` <span class="badge" title="Lançamento recorrente">${x.recurrence_active?"Recorrente":"Recorrência encerrada"}${x.recurrence_frequency?" · "+FREQ[x.recurrence_frequency]:""}</span>`:""}</td><td data-label="Categoria">${esc(x.category)}</td><td data-label="Data">${brdate(x.date)}</td><td data-label="Tipo">${x.type==="receita"?"Receita":"Despesa"}</td><td data-label="Valor"><b class="value ${x.type==="receita"?"in":"out"}">${x.type==="receita"?"+":"−"} ${money(x.amount_cents)}</b></td><td data-label="Ações"><button class="btn small" data-edit="${x.id}">Editar</button> <button class="btn small danger" data-del="${x.id}">Excluir</button></td></tr>`).join("");
    $("#txEmpty").classList.toggle("hidden",r.items.length>0);$("#txCount").textContent=`${r.total} registro(s)`;$("#txPrev").disabled=state.txPage<=1;$("#txNext").disabled=state.txPage*state.txPageSize>=r.total;
  }catch(e){toast(e.message,false)}
}
$("#txTabs").onclick=e=>{const b=e.target.closest("button");if(!b)return;state.txType=b.dataset.type;state.txPage=1;$$("#txTabs button").forEach(x=>x.classList.toggle("active",x===b));loadTransactions()};
$("#txApply").onclick=()=>{state.txPage=1;loadTransactions()};$("#txClear").onclick=()=>{$("#txSearch").value="";$("#txStart").value="";$("#txEnd").value="";state.txType="";state.txPage=1;$$("#txTabs button").forEach((x,i)=>x.classList.toggle("active",i===0));loadTransactions()};
$("#txPrev").onclick=()=>{state.txPage--;loadTransactions()};$("#txNext").onclick=()=>{state.txPage++;loadTransactions()};
$("#txBody").onclick=async e=>{const ed=e.target.dataset.edit,del=e.target.dataset.del;if(ed){openTx(txCache.find(x=>x.id===ed));return}
  if(!del)return;const tx=txCache.find(x=>x.id===del);if(!confirm(`Excluir "${tx?.description||"esta transação"}"? Os resumos serão recalculados.`))return;
  let scope="single";
  if(tx?.recurrence_id&&tx.recurrence_active&&confirm("Esta transação é recorrente.\n\nOK: excluir esta e as próximas ocorrências e encerrar a recorrência.\nCancelar: excluir somente esta ocorrência."))scope="future";
  try{const r=await api(`/api/transactions/${del}?scope=${scope}`,{method:"DELETE"});toast(scope==="future"?`${r.deleted} ocorrência(s) excluída(s) e recorrência encerrada.`:"Transação excluída.");loadTransactions();loadDashboard()}catch(err){toast(err.message,false)}};

function openGoal(g=null){$("#goalForm").reset();$("#goalId").value=g?.id||"";$("#goalModalTitle").textContent=g?"Editar meta":"Nova meta";$("#goalTitle").value=g?.title||"";$("#goalDescription").value=g?.description||"";$("#goalTarget").value=g?(g.target_cents/100).toFixed(2).replace(".",","):"";$("#goalDeadline").value=g?.deadline||"";$("#goalStatus").textContent="";modal("goalModal")}
$("#newGoalBtn").onclick=()=>openGoal();$("#firstGoalBtn").onclick=()=>openGoal();
$("#goalForm").onsubmit=async e=>{e.preventDefault();const id=$("#goalId").value;try{await api(id?"/api/goals/"+id:"/api/goals",{method:id?"PUT":"POST",body:{title:$("#goalTitle").value,description:$("#goalDescription").value||null,target:$("#goalTarget").value,deadline:$("#goalDeadline").value}});modal("goalModal",false);toast(id?"Meta atualizada.":"Meta criada.");loadGoals();loadDashboard()}catch(err){$("#goalStatus").textContent=err.message}};
function amount(gid,kind){const g=goalsCache.find(x=>x.id===gid);state.amountAction={gid,kind};$("#amountTitle").textContent=kind==="reserve"?"Reservar valor":"Retirar reserva";$("#amountHint").textContent=kind==="reserve"?`Disponível para reservar: ${money(state.goalBalances?.available)}. Reservar não cria despesa.`:`Reservado nesta meta: ${money(g?.reserved_cents)}. O valor volta para o disponível.`;$("#amountValue").value="";$("#amountStatus").textContent="";modal("amountModal");setTimeout(()=>$("#amountValue").focus(),60)}
$("#amountConfirm").onclick=async()=>{const a=state.amountAction,b=$("#amountConfirm");if(b.disabled)return;b.disabled=true;try{await api(`/api/goals/${a.gid}/${a.kind}`,{method:"POST",body:{amount:$("#amountValue").value}});modal("amountModal",false);toast(a.kind==="reserve"?"Valor reservado.":"Reserva retirada.");loadGoals();loadDashboard()}catch(e){$("#amountStatus").textContent=e.message}finally{b.disabled=false}};
let goalsCache=[];
async function loadGoals(){
  try{const r=await api("/api/goals");goalsCache=r.items;state.goalBalances=r;$("#gBalance").textContent=money(r.balance_total);$("#gReserved").textContent=money(r.reserved);$("#gAvailable").textContent=money(r.available);
    $("#goalsEmpty").classList.toggle("hidden",r.items.length>0);
    const ST={ativa:["Em andamento",""],pronta:["Reserva suficiente","good"],vencida:["Prazo vencido","bad"],concluida:["Concluída","good"]};
    $("#goalsGrid").innerHTML=r.items.map(g=>{const [label,cls]=ST[g.state]||ST.ativa,open=g.status==="ativa";
      const when=g.state==="concluida"?"":g.days_left<0?` • venceu há ${-g.days_left} dia(s)`:g.days_left===0?" • vence hoje":` • ${g.days_left} dia(s) restantes`;
      return`<article class="card goal"><div class="goal-top"><div><h3>${esc(g.title)}</h3><div class="muted">${esc(g.description||"Sem descrição")}</div></div><span class="badge ${cls}">${label}</span></div><div><div style="display:flex;justify-content:space-between"><b>${money(g.reserved_cents)}</b><span class="muted">de ${money(g.target_cents)}</span></div><div class="progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${g.percent}" aria-label="Progresso da meta ${esc(g.title)}" style="margin:8px 0"><i style="width:${g.percent}%"></i></div><div class="muted">${g.percent}% • faltam ${money(g.remaining_cents)}</div><div class="muted" style="font-size:12px;margin-top:4px">Prazo: ${brdate(g.deadline)}${when}</div></div><div class="goal-actions">${open?`<button class="btn small" data-res="${g.id}">Reservar</button>`:""}${g.reserved_cents>0?`<button class="btn small" data-with="${g.id}">Retirar</button>`:""}${open?`<button class="btn small" data-g-edit="${g.id}">Editar</button><button class="btn small" data-complete="${g.id}">Concluir</button>`:""}<button class="btn small danger" data-g-del="${g.id}">Excluir</button></div></article>`}).join("")}catch(e){toast(e.message,false)}
}
$("#goalsGrid").onclick=async e=>{const d=e.target.dataset;if(d.res)return amount(d.res,"reserve");if(d.with)return amount(d.with,"withdraw");if(d.gEdit)return openGoal(goalsCache.find(x=>x.id===d.gEdit));
  try{
    if(d.complete&&confirm("Marcar a meta como concluída? Nenhuma despesa é criada; o valor reservado continua separado até você retirá-lo.")){const r=await api(`/api/goals/${d.complete}/complete`,{method:"POST"});toast(r.message);loadGoals();loadDashboard();return}
    if(d.gDel&&confirm("Excluir a meta? Esta ação não pode ser desfeita. O valor reservado volta para o disponível; o saldo total não muda.")){const r=await api(`/api/goals/${d.gDel}`,{method:"DELETE"});toast(r.message);loadGoals();loadDashboard()}
  }catch(err){toast(err.message,false)}};

/* ===== Educação: trilha por níveis + player de aula ===== */
const edu={mods:[],prog:{},pass:70,flat:[],cur:null};
const eduKey=(m,t)=>m+":"+t;
const eduP=(m,t)=>edu.prog[eduKey(m,t)];
const eduDone=(m,t)=>eduP(m,t)?.status==="concluida";
const eduAttempts=p=>{try{return JSON.parse(p?.answers_json||"{}").attempts||0}catch{return 0}};
function eduUnlocked(i){return i===0||eduDone(edu.flat[i-1].m,edu.flat[i-1].t)}


async function loadEducation(){
  try{
    const r=await api("/api/education");
    edu.mods=r.modules;edu.pass=r.pass||70;edu.prog=Object.fromEntries((r.progress||[]).map(x=>[eduKey(x.module_key,x.topic_key),x]));
    edu.flat=[];r.modules.forEach(m=>m.topics.forEach(t=>edu.flat.push({m:m.key,t:t.key,mod:m,topic:t})));
  }catch(e){
    toast(e.message,false);
    return;
  }
  renderTrail();
}

function renderTrail(){
  $("#lessonView").classList.add("hidden");$("#modules").classList.remove("hidden");$("#eduTop").classList.remove("hidden");
  const total=edu.flat.length,done=edu.flat.filter(x=>eduDone(x.m,x.t)).length;
  const next=edu.flat.find(x=>!eduDone(x.m,x.t));
  $("#eduTop").innerHTML=`<div class="card edu-hero"><div><small class="muted">Continuar aprendendo</small>
    <h2>${next?esc(next.topic.title):"Curso concluído 🎉"}</h2>
    <p class="muted">${next?`Nível ${next.mod.level} · ${esc(next.mod.title)}`:"Você concluiu todas as aulas. Revise quando quiser."}</p></div>
    <div class="edu-hero-r"><div class="progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(done/total*100)}" aria-label="Progresso no curso"><i style="width:${done/total*100}%"></i></div>
    <small class="muted">${done} de ${total} aulas concluídas</small>
    ${next?`<button class="btn primary" data-open="${next.m}:${next.t}">${done?"Continuar":"Começar o curso"}</button>`:""}</div></div>`;
  let idx=-1;
  $("#modules").innerHTML=edu.mods.map(m=>{
    const dn=m.topics.filter(t=>eduDone(m.key,t.key)).length;
    return `<article class="card level"><div class="level-head"><span class="badge">Nível ${m.level} · ${esc(m.level_name)}</span><small class="muted">${dn}/${m.topics.length} aulas</small></div>
    <h3>${esc(m.title)}</h3><p class="muted">${esc(m.description)}</p>
    <div class="progress" style="margin:12px 0"><i style="width:${dn/m.topics.length*100}%"></i></div>
    <ol class="steps">${m.topics.map((t,k)=>{idx++;const p=eduP(m.key,t.key),dn2=eduDone(m.key,t.key),lk=!eduUnlocked(idx),ip=p&&!dn2;
      const st=dn2?`Concluída · ${p.score}%`:lk?"Bloqueada até concluir a anterior":ip?"Em andamento":"Disponível";
      return `<li><button class="step ${dn2?"done":""} ${lk?"locked":""}" data-open="${m.key}:${t.key}" data-locked="${lk?1:0}"><span class="num" aria-hidden="true">${dn2?"✓":lk?"🔒":k+1}</span><span class="st-t"><b>${esc(t.title)}</b><small>${st}</small></span><span class="st-n" aria-hidden="true">${t.activity_count ?? t.acts.length} atividades</span></button></li>`}).join("")}</ol></article>`}).join("");
}

$("#eduTop").onclick=$("#modules").onclick=e=>{
  const b=e.target.closest("[data-open]");if(!b)return;
  if(b.dataset.locked==="1"&&!confirm("Esta aula é de um passo mais à frente na trilha. Recomendamos concluir a anterior primeiro. Abrir mesmo assim?"))return;
  const [m,t]=b.dataset.open.split(":");openLesson(m,t);
};

function openLesson(m,t){
  const f=edu.flat.find(x=>x.m===m&&x.t===t);if(!f)return;
  if(f.mod.intro && !f.mod.intro.completed){FinTrackIntro.open(m,t);return;}
  edu.cur={...f,step:0,ans:f.topic.acts.map(()=>null),res:f.topic.acts.map(()=>null),result:null,busy:false};
  if(!eduP(m,t)){
    api(`/api/education/${m}/${t}`,{method:"PUT",body:{status:"em_andamento"}}).then(()=>{edu.prog[eduKey(m,t)]={status:"em_andamento",module_key:m,topic_key:t}}).catch(()=>{});
  }
  $("#modules").classList.add("hidden");$("#eduTop").classList.add("hidden");$("#lessonView").classList.remove("hidden");
  renderStep();scrollTo({top:0,behavior:"smooth"});
}

function stepNav(){
  const c=edu.cur,n=c.topic.acts.length;
  const labels=["Aula",...c.topic.acts.map((_,i)=>"Atividade "+(i+1)),"Resultado"];
  return `<div class="lv-top"><button class="btn ghost small" data-back>← Trilha</button><span class="badge">Nível ${c.mod.level} · ${esc(c.mod.title)}</span></div>
  <ol class="dots" aria-label="Etapas da aula">${labels.map((l,i)=>`<li class="${i<c.step?"past":i===c.step?"now":""}" ${i===c.step?'aria-current="step"':""}><span class="sr">${l}</span></li>`).join("")}</ol>`;
}

function renderStep(){
  const c=edu.cur,acts=c.topic.acts,n=acts.length,t=c.topic;let body="";
  if(c.step===0){
    body=`<span class="chip">Objetivo</span><h2>${esc(t.title)}</h2><p class="lead2">${esc(t.goal)}</p>
    <p>${esc(t.explain)}</p><div class="example"><b>Exemplo do dia a dia</b><p>${esc(t.example)}</p></div>
    <p class="muted" style="font-size:12px">${n} atividades · acerte pelo menos ${edu.pass}% para concluir a aula</p>
    <button class="btn primary" data-go="1">Começar atividades</button>`;
  }else if(c.step<=n){
    const i=c.step-1,a=acts[i],r=c.res[i];
    body=`<span class="chip">Atividade ${c.step} de ${n}</span><form id="actForm" onsubmit="return false"><fieldset ${r?"disabled":""}><legend>${esc(a.q)}</legend>${actInput(a,i)}</fieldset></form>
    <div id="fb" aria-live="polite">${r?feedback(r):""}</div>
    <div class="act-btns">${r?`<button class="btn primary" data-go="${c.step+1}">${c.step<n?"Próxima atividade":"Ver resultado"}</button>`:`<button class="btn primary" id="btnCheck" data-check disabled>Verificar</button>`}</div>`;
  }else{
    body=resultView();
  }
  $("#lessonView").innerHTML=`<div class="card lv">${stepNav()}<div class="stepbody" key="${c.step}">${body}</div></div>`;
  budSum();syncCheck();
  const f=$("#lessonView .stepbody h2,#lessonView legend");f&&(f.tabIndex=-1,f.focus({preventScroll:true}));
  if(c.step===n+1&&c.result?.passed)celebrate();
}

function actInput(a,i){
  const prev=edu.cur.ans[i],dis=edu.cur.res[i];
  if(a.t==="quiz")return `<div class="opts">${a.opts.map((o,k)=>`<label class="opt"><input type="radio" name="q" value="${k}" ${prev===k?"checked":""}><span>${esc(o)}</span></label>`).join("")}</div>`;
  if(a.t==="multi")return `<p class="muted" style="font-size:12px;margin:0 0 8px">Marque todas as corretas.</p><div class="opts">${a.opts.map((o,k)=>`<label class="opt"><input type="checkbox" name="q" value="${k}" ${prev?.includes(k)?"checked":""}><span>${esc(o)}</span></label>`).join("")}</div>`;
  if(a.t==="classify"){const p=prev||[];return `<div class="classify">${a.items.map((it,k)=>`<div class="crow"><span>${esc(it)}</span><div class="seg" role="group" aria-label="${esc(it)}">${a.buckets.map((b,j)=>`<button type="button" class="${p[k]===j?"on":""}" data-cl="${k}:${j}" aria-pressed="${p[k]===j}">${esc(b)}</button>`).join("")}</div></div>`).join("")}</div>`}
  if(a.t==="calc")return `<label class="calc"><span>${esc(a.unit)}</span><input class="input" type="text" inputmode="decimal" autocomplete="off" maxlength="20" name="q" value="${esc(prev??"")}" aria-label="Sua resposta em reais" placeholder="Ex.: 1.200,00"></label>`;
  if(a.t==="budget"){const p=prev||a.cats.map(()=>0);return `<p class="muted" style="margin:0 0 10px">Renda: <b>${esc(a.total)}</b></p>${a.cats.map((c,k)=>`<div class="bud"><label for="b${k}">${esc(c)}</label><input id="b${k}" type="range" min="0" max="100" step="5" value="${p[k]}" data-bud="${k}"><output id="bo${k}">${p[k]}%</output></div>`).join("")}<p class="bud-sum" id="budSum" aria-live="polite"></p>`}
  return "";
}

function readAns(a){
  const f=$("#actForm");if(!f)return null;
  if(a.t==="quiz"){const x=f.querySelector("input:checked");return x?+x.value:null}
  if(a.t==="multi"){const x=[...f.querySelectorAll("input:checked")].map(i=>+i.value);return x.length?x:null}
  if(a.t==="classify"){if(!f.querySelector(".crow"))return null;const on=[...f.querySelectorAll(".crow")].map(r=>{const b=r.querySelector("button.on");return b?+b.dataset.cl.split(":")[1]:null});return on.every(v=>v!==null)?on:null}
  if(a.t==="calc"){const v=(f.querySelector("input")?.value||"").trim();return v===""?null:v}
  if(a.t==="budget"){const v=[...f.querySelectorAll("[data-bud]")].map(i=>+i.value);return v.reduce((s,x)=>s+x,0)===100?v:null}
}
function budSum(){const el=$("#budSum");if(!el)return;const v=[...$$("[data-bud]")].map(i=>+i.value),s=v.reduce((a,b)=>a+b,0);v.forEach((x,k)=>$("#bo"+k).textContent=x+"%");el.textContent=s===100?"Soma: 100% ✓":`Soma: ${s}% — a soma precisa fechar 100%`;el.className="bud-sum "+(s===100?"ok":"")}

function feedback(r){return `<div class="fb ${r.ok?"ok":r.fraction>0?"part":"bad"}" role="status"><b>${r.ok?"Correto!":r.fraction>0?"Quase lá — parte certa.":"Não foi dessa vez."}</b><p>${esc(r.why)}</p>${r.ok?"":`<p class="right"><small>Resposta esperada</small><br>${esc(r.right)}</p>`}</div>`}

function resultView(){
  const c=edu.cur,r=c.result,t=c.topic,ni=edu.flat.findIndex(x=>x.m===c.m&&x.t===c.t)+1,nx=edu.flat[ni];
  if(!r)return `<div class="skeleton" style="height:120px"></div>`;
  return `<div class="res-top"><div class="ring" style="--p:${r.score}"><span>${r.score}%</span></div><div>
    <h2>${r.passed?"Aula concluída!":r.completed?"Aula já concluída — nova tentativa":"Ainda não foi dessa vez"}</h2>
    <p class="muted">${r.passed?`Você atingiu ${r.score}% (mínimo ${edu.pass}%). Progresso salvo.`:`Você fez ${r.score}%. Precisa de ${edu.pass}% para concluir. Releia a aula e tente de novo.`} · Tentativa ${r.attempts}</p></div></div>
    <h3 style="margin:18px 0 8px">Correção comentada</h3>
    <ul class="review">${t.acts.map((a,i)=>`<li class="${r.results[i].ok?"ok":"bad"}"><b>${r.results[i].ok?"✓":"✗"} ${esc(a.q)}</b><p>${esc(r.results[i].why)}</p></li>`).join("")}</ul>
    <h3 style="margin:18px 0 8px">Resumo</h3><ul class="sum">${t.summary.map(s=>`<li>${esc(s)}</li>`).join("")}</ul>
    <p class="muted" style="font-size:12px;margin-top:14px">Fontes: ${t.sources.map(s=>`<a href="${esc(s.u)}" target="_blank" rel="noopener" style="color:var(--green)">${esc(s.n)}</a>`).join(" · ")}. Conteúdo introdutório, revisado em ${t.reviewed.slice(5)}/${t.reviewed.slice(0,4)}. Confira dados que mudam com o tempo nas fontes oficiais.</p>
    <div class="act-btns">${r.passed&&nx?`<button class="btn primary" data-open2="${nx.m}:${nx.t}">Próxima aula</button>`:""}<button class="btn ${r.passed?"":"primary"}" data-retry>Refazer atividades</button><button class="btn ghost" data-back>Voltar à trilha</button></div>`;
}

function celebrate(){
  if(matchMedia("(prefers-reduced-motion:reduce)").matches)return;
  const r=$("#lessonView .ring");r&&r.classList.add("pop");
}

$("#lessonView").addEventListener("click",async e=>{
  const c=edu.cur;if(!c)return;const acts=c.topic.acts;
  if(e.target.closest("[data-back]")){await loadEducation();return}
  const g=e.target.closest("[data-go]");
  if(g){c.step=+g.dataset.go;if(c.step===acts.length+1)return finishLesson();renderStep();return}
  const o2=e.target.closest("[data-open2]");if(o2){const [m,t]=o2.dataset.open2.split(":");await loadEducation();openLesson(m,t);return}
  if(e.target.closest("[data-retry]")){c.ans=acts.map(()=>null);c.res=acts.map(()=>null);c.result=null;c.step=1;renderStep();return}
  const cl=e.target.closest("[data-cl]");
  if(cl){const [k,j]=cl.dataset.cl.split(":");cl.parentElement.querySelectorAll("button").forEach(b=>{b.classList.remove("on");b.setAttribute("aria-pressed","false")});cl.classList.add("on");cl.setAttribute("aria-pressed","true");syncCheck();return}
  if(e.target.closest("[data-check]")){
    const i=c.step-1,a=acts[i],ans=readAns(a);if(ans==null||c.busy)return;c.busy=true;
    const btn=$("#btnCheck");btn.disabled=true;btn.textContent="Corrigindo…";
    try{
      const r=await api(`/api/education/${c.m}/${c.t}/check`,{method:"POST",body:{i,answer:ans}});
      c.ans[i]=ans;c.res[i]=r;renderStep();const fb=$("#fb");fb&&fb.scrollIntoView({block:"nearest",behavior:"smooth"})
    }catch(err){toast(err.message,false);btn.disabled=false;btn.textContent="Verificar"}
    c.busy=false;
  }
});
function syncCheck(){const c=edu.cur;if(!c||c.step<1||c.step>c.topic.acts.length)return;const b=$("#btnCheck");if(b)b.disabled=readAns(c.topic.acts[c.step-1])==null}
$("#lessonView").addEventListener("input",e=>{if(e.target.matches("[data-bud]"))budSum();syncCheck()});
$("#lessonView").addEventListener("change",syncCheck);

async function finishLesson(){
  const c=edu.cur;c.result=null;renderStep();
  try{
    const r=await api(`/api/education/${c.m}/${c.t}/submit`,{method:"POST",body:{answers:c.ans}});
    c.result=r;edu.prog[eduKey(c.m,c.t)]={module_key:c.m,topic_key:c.t,status:r.completed?"concluida":"em_andamento",score:r.best,answers_json:JSON.stringify({attempts:r.attempts})};
    renderStep();
  }catch(err){toast(err.message,false);c.step=c.topic.acts.length;renderStep()}
}

async function loadAIStatus(){
  const el=$("#aiStatus");if(!el)return;
  try{
    const s=await api("/api/ai/status");
    el.classList.toggle("ready",!!s.configured);el.classList.toggle("offline",!s.configured);
    el.querySelector("span").textContent=s.configured?`IA configurada${s.model?" • "+s.model:""}`:"IA indisponível · não configurada no servidor";
    $("#chatInput").placeholder=s.configured?"Digite sua mensagem...":"A IA não está configurada. Suas mensagens ficam salvas, mas não haverá resposta automática.";
  }catch(e){
    el.classList.add("offline");el.classList.remove("ready");el.querySelector("span").textContent="Status indisponível";
  }
}
async function loadConversations(){
  loadAIStatus();
  try{const r=await api("/api/ai/conversations");renderConversations(r.items);if(!state.currentConversation&&r.items.length){state.currentConversation=r.items[0].id;loadConversation(state.currentConversation)}}catch(e){toast(e.message,false)}
}
function renderConversations(items){const q=$("#convSearch").value.toLowerCase();$("#conversationList").innerHTML=items.filter(x=>x.title.toLowerCase().includes(q)).map(x=>`<div style="display:grid;grid-template-columns:1fr auto auto;gap:4px;align-items:center;margin-bottom:4px"><button class="conv ${x.id===state.currentConversation?"active":""}" data-cid="${x.id}">${esc(x.title)}<div style="font-size:10px">${new Date(x.updated_at).toLocaleDateString("pt-BR")}</div></button><button class="btn small ghost" data-cren="${x.id}" title="Renomear">✎</button><button class="btn small ghost danger" data-cdel="${x.id}" title="Excluir">×</button></div>`).join("")}
$("#convSearch").oninput=loadConversations;$("#conversationList").onclick=async e=>{const b=e.target.closest("[data-cid]");if(b){state.currentConversation=b.dataset.cid;loadConversation(b.dataset.cid);loadConversations();return}const rid=e.target.closest("[data-cren]")?.dataset.cren;if(rid){const title=prompt("Novo título da conversa:");if(title){await api("/api/ai/conversations/"+rid,{method:"PATCH",body:{title}});toast("Conversa renomeada.");loadConversations()}return}const did=e.target.closest("[data-cdel]")?.dataset.cdel;if(did&&confirm("Excluir esta conversa?")){await api("/api/ai/conversations/"+did,{method:"DELETE"});if(state.currentConversation===did){state.currentConversation=null;$("#messages").innerHTML='<div class="bubble assistant">Conversa excluída. Crie ou abra outra conversa.</div>'}toast("Conversa excluída.");loadConversations()}};
$("#newConversation").onclick=async()=>{const r=await api("/api/ai/conversations",{method:"POST"});state.currentConversation=r.id;$("#messages").innerHTML='<div class="bubble assistant">Nova conversa iniciada. O que você quer entender hoje?</div>';loadConversations()};
async function loadConversation(cid){const r=await api("/api/ai/conversations/"+cid);$("#messages").innerHTML=r.messages.map(m=>`<div class="bubble ${m.role}">${esc(m.content)}</div>`).join("")||'<div class="bubble assistant">Conversa vazia. Envie sua primeira mensagem.</div>';$("#messages").scrollTop=$("#messages").scrollHeight}
async function ensureConversation(){if(state.currentConversation)return state.currentConversation;const r=await api("/api/ai/conversations",{method:"POST"});state.currentConversation=r.id;return r.id}
async function sendChat(text,requestKey=null,renderUser=true){
  text=(text||$("#chatInput").value).trim();if(!text)return;
  const cid=await ensureConversation(),key=requestKey||uuid();
  if(renderUser){
    $("#chatInput").value="";
    $("#messages").insertAdjacentHTML("beforeend",`<div class="bubble user">${esc(text)}</div>`);
  }
  $("#thinking")?.remove();
  $("#messages").insertAdjacentHTML("beforeend",`<div class="bubble assistant" id="thinking">Processando…</div>`);
  $("#messages").scrollTop=$("#messages").scrollHeight;$("#sendMessage").disabled=true;
  try{
    const r=await api(`/api/ai/conversations/${cid}/messages`,{method:"POST",body:{content:text,request_key:key}});
    $("#thinking")?.remove();
    if(r.assistant_message)$("#messages").insertAdjacentHTML("beforeend",`<div class="bubble assistant">${esc(r.assistant_message.content)}</div>`);
    $("#messages").scrollTop=$("#messages").scrollHeight;
    loadConversations();
  }catch(e){
    const t=$("#thinking");
    if(t){
      t.innerHTML=`<span>${esc(e.message)}</span><br><button class="btn small" id="retryAi" type="button" style="margin-top:8px">Tentar novamente</button>`;
      t.style.color="#ff9a9a";
      $("#retryAi")?.addEventListener("click",()=>sendChat(text,key,false),{once:true});
    }
  }finally{$("#sendMessage").disabled=false}
}
$("#sendMessage").onclick=()=>sendChat();$("#chatInput").onkeydown=e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();sendChat()}};$("#suggestions").onclick=e=>{const b=e.target.closest("button");if(!b)return;if(b.textContent.trim()==="Analise meus gastos."){setPage("dashboard");setTimeout(()=>$("#analyzeSpending").click(),150)}else sendChat(b.textContent.trim())};

async function loadClasses(){
  try{
    const r=await api("/api/classes");$("#classesIntro").textContent=r.role==="professor"?"Gerencie apenas as turmas sob sua responsabilidade.":"Veja suas turmas e entre por código.";
    $("#createClassBtn").classList.toggle("hidden",r.role!=="professor");$("#studentJoin").classList.toggle("hidden",r.role!=="aluno");
    $("#classesGrid").innerHTML=r.items.length?r.items.map(c=>`<article class="card classcard"><div><h3>${esc(c.name)}</h3><p class="muted">${esc(c.description||"Sem descrição")}</p></div>${r.role==="professor"?`<div><span class="muted">Código</span><div class="classcode">${c.code_active?esc(c.code):"DESATIVADO"}</div><span class="muted">${c.participants} participante(s)</span></div><div class="goal-actions"><button class="btn small" data-class-edit="${c.id}">Editar</button><button class="btn small" data-renew="${c.id}">Renovar código</button><button class="btn small" data-disable="${c.id}">Desativar código</button><button class="btn small" data-participants="${c.id}">Participantes</button><button class="btn small" data-assign="${c.id}">Atribuir aula</button><button class="btn small" data-results="${c.id}">Resultados</button><button class="btn small" data-financial-summary="${c.id}">Resumo financeiro</button></div>`:`<div><span class="muted">Professor</span><b style="display:block">${esc(c.teacher_name)}</b><span class="muted" style="font-size:12px">Resumo financeiro: ${c.share_financial?"compartilhado":"não compartilhado"} (altere em Configurações)</span></div><div class="goal-actions"><button class="btn small danger" data-leave="${c.id}">Sair da turma</button></div>`}</article>`).join(""):`<div class="empty"><b>Nenhuma turma ainda</b>${r.role==="aluno"?"Use um código para entrar.":"Crie sua primeira turma."}</div>`;
    const a=await api("/api/assignments"),AS={pendente:["Pendente",""],atrasada:["Atrasada","bad"],concluida:["Concluída","good"]};
    $("#assignmentsList").innerHTML=a.items.length?a.items.map(x=>{const st=AS[x.state];return `<div class="assign-row" style="padding:10px 0;border-bottom:1px solid var(--line);display:flex;gap:10px;justify-content:space-between;align-items:center;flex-wrap:wrap"><div style="min-width:0"><b>${esc(x.title)}</b><div class="muted">${esc(x.class_name)}${x.due_date?" • prazo "+brdate(x.due_date):" • sem prazo"}${x.instructions?" • "+esc(x.instructions):""}</div>${r.role==="professor"?`<div class="muted" style="font-size:12px">${x.done} de ${x.total} aluno(s) concluíram</div>`:""}</div><div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">${st?`<span class="badge ${st[1]}">${st[0]}${x.score!=null&&x.state==="concluida"?" · "+x.score+"%":""}</span>`:""}${r.role==="aluno"&&x.module?`<button class="btn small" data-lesson="${esc(x.module)}:${esc(x.topic)}">${x.state==="concluida"?"Revisar aula":"Abrir aula"}</button>`:""}${r.role==="professor"?`<button class="btn small danger" data-del-assign="${x.id}">Remover</button>`:""}</div></div>`}).join(""):`<div class="empty"><b>Nenhuma atividade atribuída</b>${r.role==="professor"?"Use “Atribuir aula” em uma turma.":"Quando o professor atribuir aulas, elas aparecerão aqui."}</div>`;
  }catch(e){toast(e.message,false)}
}
$("#createClassBtn").onclick=()=>{$("#className").value="";$("#classDescription").value="";$("#classStatus").textContent="";modal("classModal")};
$("#classCreateConfirm").onclick=async()=>{const b=$("#classCreateConfirm");if(b.disabled)return;b.disabled=true;try{const r=await api("/api/classes",{method:"POST",body:{name:$("#className").value,description:$("#classDescription").value||null}});modal("classModal",false);toast("Turma criada. Código: "+r.code);loadClasses()}catch(e){$("#classStatus").textContent=e.message}finally{b.disabled=false}};
$("#previewClass").onclick=async()=>{try{const r=await api("/api/classes/preview",{method:"POST",body:{code:$("#classCode").value}});const c=r.class;$("#classPreview").innerHTML=`<div class="notice" style="margin-top:10px"><b>${esc(c.name)}</b><br>Professor: ${esc(c.teacher_name)}<br>${esc(c.description||"")}${r.already_member?"<br>Você já participa desta turma.":`<br><button class="btn primary small" id="confirmJoin" style="margin-top:8px">Confirmar entrada</button>`}</div>`;$("#confirmJoin")?.addEventListener("click",async()=>{try{await api("/api/classes/join",{method:"POST",body:{code:$("#classCode").value}});toast("Entrada na turma confirmada. O compartilhamento financeiro começa desativado.");$("#classPreview").innerHTML="";$("#classCode").value="";loadClasses()}catch(err){$("#classPreview").innerHTML=`<div class="notice error">${esc(err.message)}</div>`}})}catch(e){$("#classPreview").innerHTML=`<div class="notice error">${esc(e.message)}</div>`}};

async function openFinancialSummary(classId){
  try{
    const r=await api(`/api/classes/${classId}/financial-summary`);
    $("#financialSummaryPeriod").textContent=`Período: ${brdate(r.period.start)} a ${brdate(r.period.end)}`;
    const body=$("#financialSummaryBody"),empty=$("#financialSummaryEmpty");
    if(r.items.length){
      empty.classList.add("hidden");
      body.innerHTML=r.items.map(x=>`<tr><td data-label="Aluno"><b>${esc(x.student_name)}</b></td><td data-label="Receitas" class="value in">${money(x.receitas)}</td><td data-label="Despesas" class="value out">${money(x.despesas)}</td><td data-label="Resultado">${money(x.resultado)}</td><td data-label="Registros">${x.registros}</td></tr>`).join("");
    }else{
      body.innerHTML="";empty.classList.remove("hidden");
    }
    modal("financialSummaryModal");
  }catch(e){toast(e.message,false)}
}

function infoModal(title,html){$("#infoTitle").textContent=title;$("#infoBody").innerHTML=html;modal("infoModal")}
$("#assignmentsList").onclick=async e=>{const l=e.target.closest("[data-lesson]");if(l){const [m,t]=l.dataset.lesson.split(":");setPage("education");await loadEducation();openLesson(m,t);return}
  const d=e.target.closest("[data-del-assign]");if(d&&confirm("Remover esta atividade da turma? O progresso dos alunos na aula continua salvo.")){try{await api("/api/assignments/"+d.dataset.delAssign,{method:"DELETE"});toast("Atividade removida.");loadClasses()}catch(err){toast(err.message,false)}}};
let lessonsCatalog=null;
async function openAssign(cid){
  try{lessonsCatalog=lessonsCatalog||(await api("/api/lessons")).items}catch(e){toast(e.message,false);return}
  $("#assignClass").value=cid;$("#assignDue").value="";$("#assignDue").min=todayBR();$("#assignInstructions").value="";$("#assignStatus").textContent="";
  $("#assignLesson").innerHTML=lessonsCatalog.map(l=>`<option value="${esc(l.key)}">Nível ${l.level} · ${esc(l.module_title)} — ${esc(l.title)}</option>`).join("");
  modal("assignModal");
}
$("#assignForm").onsubmit=async e=>{e.preventDefault();const b=$("#assignSubmit");b.disabled=true;$("#assignStatus").textContent="";
  try{await api(`/api/classes/${$("#assignClass").value}/assignments`,{method:"POST",body:{content_key:$("#assignLesson").value,due_date:$("#assignDue").value||null,instructions:$("#assignInstructions").value||null}});modal("assignModal",false);toast("Aula atribuída à turma.");loadClasses()}
  catch(err){$("#assignStatus").textContent=err.message}finally{b.disabled=false}};
$("#classesGrid").onclick=async e=>{const d=e.target.dataset;
  if(d.leave){if(confirm("Sair desta turma? O professor deixa de ver suas atividades nesta turma e o compartilhamento é encerrado. Seu progresso nas aulas continua salvo.")){try{await api(`/api/classes/${d.leave}/membership`,{method:"DELETE"});toast("Você saiu da turma.");loadClasses()}catch(err){toast(err.message,false)}}return}
  if(d.assign){openAssign(d.assign);return}
  if(d.participants){try{const r=await api(`/api/classes/${d.participants}/participants`);infoModal("Participantes",r.items.length?`<div class="tablewrap"><table class="table"><thead><tr><th>Aluno</th><th>E-mail</th><th>Entrou em</th><th>Resumo financeiro</th></tr></thead><tbody>${r.items.map(x=>`<tr><td data-label="Aluno"><b>${esc(x.name)}</b></td><td data-label="E-mail">${esc(x.email)}</td><td data-label="Entrou em">${brdate(String(x.created_at).slice(0,10))}</td><td data-label="Resumo financeiro">${x.share_financial?"Autorizado":"Não autorizado"}</td></tr>`).join("")}</tbody></table></div>`:`<div class="empty"><b>Nenhum participante ainda</b>Compartilhe o código da turma com os alunos.</div>`)}catch(err){toast(err.message,false)}return}
  if(d.results){try{const r=await api(`/api/classes/${d.results}/assignment-results`),L={pendente:"Pendente",atrasada:"Atrasada",concluida:"Concluída"};infoModal("Resultados das atividades",r.items.length?`<div class="tablewrap"><table class="table"><thead><tr><th>Aluno</th><th>Aula</th><th>Prazo</th><th>Status</th><th>Pontuação</th></tr></thead><tbody>${r.items.map(x=>`<tr><td data-label="Aluno"><b>${esc(x.student_name)}</b></td><td data-label="Aula">${esc(x.title)}</td><td data-label="Prazo">${x.due_date?brdate(x.due_date):"—"}</td><td data-label="Status">${L[x.state]}</td><td data-label="Pontuação">${x.score!=null?x.score+"%":"—"}</td></tr>`).join("")}</tbody></table></div>`:`<div class="empty"><b>Ainda não há resultados</b>Atribua uma aula para acompanhar a turma.</div>`)}catch(err){toast(err.message,false)}return}
  try{
  if(d.financialSummary){await openFinancialSummary(d.financialSummary);return}if(d.classEdit){const current=([...document.querySelectorAll("[data-class-edit]")].find(x=>x.dataset.classEdit===d.classEdit)?.closest(".classcard"));const name=prompt("Novo nome da turma:",current?.querySelector("h3")?.textContent||"");if(name){const description=prompt("Descrição da turma:",current?.querySelector("p")?.textContent||"");await api(`/api/classes/${d.classEdit}`,{method:"PUT",body:{name,description}});toast("Turma atualizada.");loadClasses()}return}if(d.renew){const r=await api(`/api/classes/${d.renew}/code/renew`,{method:"POST"});toast("Novo código: "+r.code);loadClasses()}if(d.disable&&confirm("Desativar este código de entrada?")){await api(`/api/classes/${d.disable}/code/disable`,{method:"POST"});toast("Código desativado.");loadClasses()}}catch(err){toast(err.message,false)}};

function setSwitch(el,on){el.classList.toggle("on",!!on);el.setAttribute("aria-pressed",String(!!on))}
async function loadSettings(){
  state.me=await api("/api/auth/me");paintAvatar($("#profileAvatar"),state.me.avatar,state.me.id);$("#profileName").value=state.me.name;$("#profileEmail").value=state.me.email;
  $("#profileAuth").textContent=[state.me.has_password?"E-mail e senha":"",state.me.google_linked?"Google":""].filter(Boolean).join(" + ")+(state.me.email_verified?" · e-mail confirmado":"");
  setSwitch($("#themeSwitch"),state.me.settings.theme==="light");setSwitch($("#tipsSwitch"),!!state.me.settings.tips);setSwitch($("#goalsSwitch"),!!state.me.settings.goal_alerts);setSwitch($("#weeklySwitch"),!!state.me.settings.weekly_email);
  try{const h=await api("/api/health");$("#weeklySwitch").disabled=!h.email_ready&&!state.me.settings.weekly_email;$("#weeklyNote").textContent=h.email_ready?"Enviado às segundas-feiras para o seu e-mail, com os totais da semana anterior.":"Indisponível: o envio de e-mails não está configurado neste servidor."}catch{}
  if(state.me.role==="aluno"){const c=await api("/api/classes");$("#privacyClasses").innerHTML=c.items.length?c.items.map(x=>`<div class="switchrow"><div><b>${esc(x.name)}</b><div class="muted">Professor: ${esc(x.teacher_name)} • compartilhar apenas resumos financeiros autorizados</div></div><button class="switch ${x.share_financial?"on":""}" data-share="${x.id}" aria-label="Compartilhar resumo financeiro com a turma ${esc(x.name)}" aria-pressed="${!!x.share_financial}"><i></i></button></div>`).join(""):`<div class="empty">Você ainda não participa de turmas.</div>`}else $("#privacyClasses").innerHTML='<div class="notice">Professores não ativam este acesso pelo próprio perfil. Cada aluno controla o consentimento por turma.</div>';
}
async function saveSettings(patch){try{const r=await api("/api/settings",{method:"PUT",body:patch});state.me.settings=r.settings;document.documentElement.dataset.theme=r.settings.theme;if(state.dashboardData)requestAnimationFrame(()=>renderFinanceChart(state.dashboardData,state.chartType,false));toast("Preferência salva.")}catch(e){toast(e.message,false)}}
$("#themeSwitch").onclick=()=>saveSettings({theme:$("#themeSwitch").classList.contains("on")?"dark":"light"}).then(loadSettings);$("#tipsSwitch").onclick=()=>saveSettings({tips:!$("#tipsSwitch").classList.contains("on")}).then(loadSettings);$("#goalsSwitch").onclick=()=>saveSettings({goal_alerts:!$("#goalsSwitch").classList.contains("on")}).then(loadSettings);$("#weeklySwitch").onclick=()=>saveSettings({weekly_email:!$("#weeklySwitch").classList.contains("on")}).then(loadSettings);
$("#saveProfile").onclick=async()=>{try{const r=await api("/api/profile",{method:"PUT",body:{name:$("#profileName").value}});$("#sideName").textContent=r.name;$("#profileStatus").style.color="var(--green)";$("#profileStatus").textContent="Perfil salvo."}catch(e){$("#profileStatus").style.color="";$("#profileStatus").textContent=e.message}};
$("#privacyClasses").onclick=async e=>{const b=e.target.closest("[data-share]");if(!b)return;const enabled=!b.classList.contains("on");if(enabled&&!confirm("Compartilhar com o professor desta turma apenas o total de receitas, despesas, resultado e número de lançamentos do período? Descrições, comprovantes e conversas com o FinBot não são compartilhados. Você pode revogar a qualquer momento."))return;try{await api(`/api/classes/${b.dataset.share}/share`,{method:"PUT",body:{enabled}});setSwitch(b,enabled);toast(enabled?"Compartilhamento ativado para esta turma.":"Compartilhamento revogado.")}catch(err){toast(err.message,false)}};

$("#scanBtn").onclick=async()=>{try{const h=await api("/api/health");if(!h.receipt_analysis_ready){toast("A leitura automática de comprovantes não está configurada neste servidor. Preencha a transação manualmente.",false);openTx();return}}catch{}$("#receiptFile").value="";$("#receiptPreview").classList.add("hidden");$("#receiptStatus").className="notice";$("#receiptStatus").textContent="Nada é salvo como transação até você revisar e confirmar. O FinTrack nunca pede senhas bancárias.";state.receiptId=null;modal("scanModal")};
$("#receiptFile").onchange=e=>{const f=e.target.files[0];if(!f)return;$("#receiptPreview").src=URL.createObjectURL(f);$("#receiptPreview").classList.remove("hidden")};
$("#receiptAnalyze").onclick=async()=>{
  const f=$("#receiptFile").files[0],b=$("#receiptAnalyze");if(!f){$("#receiptStatus").className="notice error";$("#receiptStatus").textContent="Selecione uma imagem.";return}
  b.disabled=true;b.textContent="Analisando...";
  try{const fd=new FormData();fd.append("image",f);const up=await api("/api/receipts/upload",{method:"POST",body:fd});state.receiptId=up.id;if(up.duplicate&&!confirm((up.warning||"Este comprovante já foi enviado.")+" Deseja analisar novamente?")){b.disabled=false;b.textContent="Analisar comprovante";return}const r=await api(`/api/receipts/${up.id}/analyze`,{method:"POST"});$("#receiptStatus").className="notice success";$("#receiptStatus").textContent="Análise recebida. Revise os campos antes de salvar.";const x=r.result||{};modal("scanModal",false);openTx();if(x.type)$$(`#txTypeTabs button`).forEach(y=>y.classList.toggle("active",y.dataset.value===x.type));fillCategory(x.type||"despesa");if(x.category)$("#txCategory").value=x.category;if(x.amount_cents)$("#txValue").value=(x.amount_cents/100).toFixed(2).replace(".",",");if(x.description)$("#txDescription").value=x.description;if(x.date)$("#txDate").value=x.date;state.txDirty=true}catch(e){$("#receiptStatus").className="notice error";$("#receiptStatus").textContent=e.message+" O preenchimento manual continua disponível."}finally{b.disabled=false;b.textContent="Analisar comprovante"}
};

window.addEventListener("beforeunload",e=>{if(state.txDirty){e.preventDefault();e.returnValue=""}});

const mascotPresets={
  dashboard:{text:"Aqui você acompanha saldo, reservas e desempenho do período. Quer um atalho?",actions:[["Nova transação","open-tx"],["Analisar gastos","analyze"],["Minhas metas","page-goals"]],tip:"Veja seu resumo"},
  transactions:{text:"Registre entradas e saídas para manter o painel sempre atualizado. Também posso te levar direto para um novo lançamento.",actions:[["Nova transação","open-tx"],["Filtrar registros","focus-tx-search"],["Voltar ao dashboard","page-dashboard"]],tip:"Adicione um lançamento"},
  goals:{text:"As metas guardam valores sem mexer no saldo total. O saldo disponível é que diminui.",actions:[["Criar meta","open-goal"],["Ver dashboard","page-dashboard"],["Nova transação","open-tx"]],tip:"Crie uma meta"},
  education:{text:"Siga a trilha por níveis: leia a aula, faça as atividades e acerte pelo menos 70% para concluir e salvar seu progresso.",actions:[["Abrir módulos","scroll-modules"],["Falar com IA","page-finbot"],["Ir para turmas","page-classes"]],tip:"Aprenda por módulos"},
  finbot:{text:"Aqui você conversa comigo com mais profundidade. Posso explicar conceitos e comentar seus dados quando essa integração estiver configurada.",actions:[["Nova conversa","new-conversation"],["Exemplos","focus-chat"],["Dashboard","page-dashboard"]],tip:"Converse comigo"},
  classes:{text:"Nesta área você entra em turmas, acompanha atividades e, se for professor, gerencia códigos e atribuições.",actions:[["Verificar código","focus-class-code"],["Criar turma","open-class"],["Configurações","page-settings"]],tip:"Gerencie turmas"},
  settings:{text:"Ajuste tema, notificações e privacidade de compartilhamento com turmas.",actions:[["Tema claro/escuro","scroll-settings"],["Editar perfil","focus-profile"],["Voltar","page-dashboard"]],tip:"Ajuste seu perfil"}
};
function initMascot(){
  const shell=$("#mascot"),toggle=$("#mascotToggle"),close=$("#mascotClose");
  if(!shell||!toggle)return;
  toggle.onclick=()=>setMascotOpen(!shell.classList.contains("open"));
  close.onclick=()=>setMascotOpen(false);
  $("#mascotActions").onclick=e=>{
    const b=e.target.closest("[data-mascot-action]");
    if(!b)return;
    runMascotAction(b.dataset.mascotAction);
  };
  if(state.me?.settings?.tips){
    setTimeout(()=>{shell.classList.add("has-tip");},600);
    setTimeout(()=>{$("#mascotTip")?.classList.add("hide");},5200);
    // Open the assistant only on request; automatic opening covered mobile forms.
  }else{
    shell.classList.remove("has-tip");
    $("#mascotTip")?.classList.add("hide");
  }
}
function setMascotOpen(open){
  const shell=$("#mascot"); if(!shell) return;
  shell.classList.toggle("open",open);
  $("#mascotToggle")?.setAttribute("aria-expanded",String(open));
}
function updateMascotContext(page,fromWelcome=false){
  const shell=$("#mascot");
  if(shell){ const hide=page==="finbot"; shell.hidden=hide; if(hide) setMascotOpen(false); }
  const preset=mascotPresets[page]||mascotPresets.dashboard;
  let text=preset.text;
  if(fromWelcome && state.me?.name){
    const first=state.me.name.split(" ")[0];
    text=`Oi, ${first}! ${preset.text}`;
  }
  const box=$("#mascotText"), actions=$("#mascotActions"), tip=$("#mascotTip");
  if(box) box.textContent=text;
  if(actions) actions.innerHTML=preset.actions.map(a=>`<button type="button" data-mascot-action="${a[1]}">${a[0]}</button>`).join("");
  if(tip){ tip.textContent=preset.tip; tip.classList.remove("hide"); setTimeout(()=>tip.classList.add("hide"),3500); }
}
function runMascotAction(action){
  if(action.startsWith("page-")){ setPage(action.replace("page-","")); return; }
  if(action==="open-tx"){ openTx(); setMascotOpen(false); return; }
  if(action==="open-goal"){ openGoal(); setMascotOpen(false); return; }
  if(action==="analyze"){ setPage("dashboard"); setTimeout(()=>$("#analyzeSpending")?.click(),140); setMascotOpen(false); return; }
  if(action==="focus-tx-search"){ setPage("transactions"); setTimeout(()=>$("#txSearch")?.focus(),120); setMascotOpen(false); return; }
  if(action==="scroll-modules"){ setPage("education"); setTimeout(()=>$("#modules")?.scrollIntoView({behavior:"smooth",block:"start"}),120); setMascotOpen(false); return; }
  if(action==="new-conversation"){ setPage("finbot"); setTimeout(()=>$("#newConversation")?.click(),140); setMascotOpen(false); return; }
  if(action==="focus-chat"){ setPage("finbot"); setTimeout(()=>$("#chatInput")?.focus(),140); setMascotOpen(false); return; }
  if(action==="focus-class-code"){ setPage("classes"); setTimeout(()=>$("#classCode")?.focus(),140); setMascotOpen(false); return; }
  if(action==="open-class"){ setPage("classes"); setTimeout(()=>$("#createClassBtn")?.click(),140); setMascotOpen(false); return; }
  if(action==="scroll-settings"){ setPage("settings"); setTimeout(()=>$("#themeSwitch")?.scrollIntoView({behavior:"smooth",block:"center"}),140); setMascotOpen(false); return; }
  if(action==="focus-profile"){ setPage("settings"); setTimeout(()=>$("#profileName")?.focus(),140); setMascotOpen(false); return; }
}

boot().catch(e=>toast(e.message,false));

/* ===== Destaques do dashboard ===== */
const RM=matchMedia("(prefers-reduced-motion:reduce)").matches;
function countTo(el,to){if(RM){el.textContent=money(to);return}const from=el._v||0,t0=performance.now();el._v=to;(function s(t){const k=Math.min(1,(t-t0)/900);el.textContent=money(from+(to-from)*(1-Math.pow(1-k,3)));if(k<1)requestAnimationFrame(s)})(t0)}
function animMetrics(d){[["#mBalance",d.balance_total],["#mIncome",d.receitas],["#mExpense",d.despesas],["#mResult",d.resultado],["#mReserved",d.reserved],["#mAvailable",d.available]].forEach(([s,v],i)=>{const el=$(s);el.parentElement.style.setProperty("--i",i);countTo(el,v)})}
const TIPS=["Regra 50/30/20: 50% para necessidades, 30% para desejos e 20% para guardar.","Antes de comprar, espere 24 horas. Muitos desejos passam sozinhos.","Comece sua reserva de emergência com pouco, mas guarde todo mês.","Pague primeiro a você: separe o valor da meta assim que o dinheiro entrar.","Revise suas assinaturas: o que você não usa há 30 dias pode sair."];
function renderHighlights(d){
  const h=new Date().getHours(),n=(state.me.name||"").split(" ")[0],has=d.receitas>0||d.despesas>0;
  $("#hdGreet").textContent=(h<12?"Bom dia":h<18?"Boa tarde":"Boa noite")+", "+n;
  const rate=d.receitas>0?Math.max(0,Math.min(100,Math.round(d.resultado/d.receitas*100))):0;
  $("#hdTitle").textContent=!has?"Vamos montar o seu painel":d.resultado>=0?"Você está no azul neste período":"Suas despesas passaram das receitas";
  $("#hdSub").textContent=!has?"Registre a primeira transação para ver números e gráficos aqui.":`Entre ${brdate(d.period.start)} e ${brdate(d.period.end)} você guardou ${rate}% do que recebeu.`;
  $("#hdRing").style.setProperty("--p",rate);$("#hdRingV").textContent=rate+"%";
  const top=d.categories[0],tot=d.categories.reduce((s,x)=>s+x.amount_cents,0),gs=d.goals.map(g=>({g,p:Math.round(g.reserved_cents/g.target_cents*100)||0})).filter(x=>x.p<100).sort((a,b)=>b.p-a.p)[0];
  const chip=(c,t,b,s)=>`<div class="chip2" style="--c:${c}"><small>${t}</small><b>${esc(b)}</b><span>${esc(s)}</span></div>`;
  $("#hdChips").innerHTML=chip("#ff8585","Maior gasto",top?top.category:"Sem despesas",top?Math.round(top.amount_cents/tot*100)+"% das despesas · "+money(top.amount_cents):"Registre uma despesa para ver")+chip("#1ed760","Meta mais próxima",gs?gs.g.title:"Nenhuma meta ativa",gs?gs.p+"% concluída · faltam "+money(Math.max(0,gs.g.target_cents-gs.g.reserved_cents)):"Crie uma meta para acompanhar")+chip("#ffd166","Dica do dia","Educação financeira",TIPS[Math.floor(Date.now()/864e5)%TIPS.length]);
}
$("#hdAdd").onclick=()=>openTx();$("#hdGoal").onclick=()=>openGoal();

/* Acessibilidade: redesenha o gráfico quando o modo de cores muda. */
document.addEventListener("fintrack:a11y",()=>{if(state.dashboardData&&typeof renderFinanceChart==="function")requestAnimationFrame(()=>renderFinanceChart(state.dashboardData,state.chartType,false))});
