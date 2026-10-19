
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
const STATIC_GITHUB_PAGES_MODE=false;
async function api(url,opt={}){
  const o={credentials:"same-origin",...opt}; if(o.body && !(o.body instanceof FormData)){o.headers={"Content-Type":"application/json",...(o.headers||{})};if(typeof o.body!=="string")o.body=JSON.stringify(o.body)}
  const r=await fetch(url,o);let j={};try{j=await r.json()}catch{}
  if(r.status===401){location.href="/login.html";throw new Error("Sessão expirada.")}
  if(!r.ok)throw new Error(j.detail||"Não foi possível concluir a operação.");
  return j
}
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
  const t=new Date(),start=new Date(t.getFullYear(),t.getMonth(),1);$("#dashStart").value=start.toISOString().slice(0,10);$("#dashEnd").value=t.toISOString().slice(0,10);
  $("#txDate").value=t.toISOString().slice(0,10);$("#recurrenceStart").value=$("#txDate").value;
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
    green:"#1ed760",
    expense:"#ff8585"
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
    maybeGoalAlert(d.goals);
    $("#recentList").innerHTML=d.recent.length?d.recent.map(x=>`<div class="tx-row"><span class="tx-ic ${x.type==="receita"?"in":"out"}">${esc((x.category||"?")[0]).toUpperCase()}</span><div class="tx-m"><b>${esc(x.description)}</b><small>${esc(x.category)} · ${brdate(x.date)}</small></div><b class="value ${x.type==="receita"?"in":"out"}">${x.type==="receita"?"+":"−"} ${money(x.amount_cents)}</b></div>`).join(""):`<div class="empty"><b>Nenhuma transação ainda</b><button class="btn primary" onclick="openTx()" style="margin-top:10px">Adicionar primeira transação</button></div>`;
    $("#dashGoals").innerHTML=d.goals.length?d.goals.map(g=>{const p=Math.min(100,Math.round((g.reserved_cents/g.target_cents)*100)||0);return`<div style="padding:9px 0"><div style="display:flex;justify-content:space-between"><b>${esc(g.title)}</b><span class="muted">${p}%</span></div><div class="progress" style="margin-top:7px"><i style="width:${p}%"></i></div></div>`}).join(""):`<div class="empty"><b>Nenhuma meta criada</b><button class="btn" onclick="setPage('goals')" style="margin-top:10px">Criar meta</button></div>`;
  }catch(e){toast(e.message,false)}
}
$("#dashApply").onclick=loadDashboard;

$("#analyzeSpending").onclick=async()=>{
  const b=$("#analyzeSpending"),box=$("#analysisBox");b.disabled=true;b.textContent="Analisando...";
  try{const r=await api("/api/ai/analyze-spending",{method:"POST"});if(!r.has_data){box.innerHTML=`<div class="notice">${esc(r.message)} <button class="btn small" onclick="setPage('transactions')">Cadastrar transação</button></div>`}else box.innerHTML=`<div class="notice success"><b>Período:</b> ${brdate(r.period.start)} a ${brdate(r.period.end)}</div><div style="white-space:pre-wrap;margin-top:10px">${esc(r.analysis)}</div>`}catch(e){box.innerHTML=`<div class="notice error">${esc(e.message)}</div>`}finally{b.disabled=false;b.textContent="Analisar meus gastos"}
};

$("#txTypeTabs").onclick=e=>{const b=e.target.closest("button");if(!b)return;$$("#txTypeTabs button").forEach(x=>x.classList.toggle("active",x===b));fillCategory(b.dataset.value);state.txDirty=true};
function currentTxType(){return $("#txTypeTabs .active").dataset.value}
function fillCategory(type=currentTxType()){if(!state.categories)return;const current=$("#txCategory").value;const arr=[...state.categories[type],...state.categories.personalizadas.filter(x=>x.type===type).map(x=>x.name)];$("#txCategory").innerHTML='<option value="">Selecione</option>'+arr.map(x=>`<option>${esc(x)}</option>`).join("");if(arr.includes(current))$("#txCategory").value=current}
function openTx(tx=null){
  $("#txForm").reset();$("#txId").value="";$("#txModalTitle").textContent=tx?"Editar transação":"Nova transação";$("#txSubmit").textContent=tx?"Salvar alterações":"Adicionar transação";$("#txFormStatus").textContent="";
  $$(`#txTypeTabs button`).forEach(x=>x.classList.toggle("active",x.dataset.value===(tx?.type||"despesa")));fillCategory(tx?.type||"despesa");
  $("#txDate").value=tx?.date||new Date().toISOString().slice(0,10);$("#recurrenceStart").value=$("#txDate").value;$("#recurrenceFields").classList.add("hidden");
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
  try{let url=id?"/api/transactions/"+id:"/api/transactions";if(id){const original=txCache.find(x=>x.id===id);if(original?.recurrence_id&&confirm("Esta transação pertence a uma recorrência. Clique em OK para aplicar as alterações também às próximas ocorrências; Cancelar altera somente esta ocorrência."))url+="?scope=future"}await api(url,{method:id?"PUT":"POST",body});state.txDirty=false;modal("txModal",false);toast(id?"Transação atualizada.":"Transação adicionada.");loadTransactions();loadDashboard()}catch(err){status.textContent=err.message}finally{b.disabled=false;b.textContent=id?"Salvar alterações":"Adicionar transação"}
};
let txCache=[];
async function loadTransactions(){
  const q=new URLSearchParams({page:state.txPage,page_size:state.txPageSize,sort:$("#txSort").value});
  if(state.txType)q.set("type",state.txType);if($("#txStart").value)q.set("start",$("#txStart").value);if($("#txEnd").value)q.set("end",$("#txEnd").value);if($("#txSearch").value.trim())q.set("q",$("#txSearch").value.trim());
  try{
    const r=await api("/api/transactions?"+q);txCache=r.items;
    $("#txSummary").textContent=`Receitas ${money(r.summary.receitas)} • Despesas ${money(r.summary.despesas)} • Resultado ${money(r.summary.resultado)}`;
    $("#txBody").innerHTML=r.items.map(x=>`<tr><td data-label="Descrição">${esc(x.description)}</td><td data-label="Categoria">${esc(x.category)}</td><td data-label="Data">${brdate(x.date)}</td><td data-label="Tipo">${x.type==="receita"?"Receita":"Despesa"}</td><td data-label="Valor"><b class="value ${x.type==="receita"?"in":"out"}">${x.type==="receita"?"+":"−"} ${money(x.amount_cents)}</b></td><td data-label="Ações"><button class="btn small" data-edit="${x.id}">Editar</button> <button class="btn small danger" data-del="${x.id}">Excluir</button></td></tr>`).join("");
    $("#txEmpty").classList.toggle("hidden",r.items.length>0);$("#txCount").textContent=`${r.total} registro(s)`;$("#txPrev").disabled=state.txPage<=1;$("#txNext").disabled=state.txPage*state.txPageSize>=r.total;
  }catch(e){toast(e.message,false)}
}
$("#txTabs").onclick=e=>{const b=e.target.closest("button");if(!b)return;state.txType=b.dataset.type;state.txPage=1;$$("#txTabs button").forEach(x=>x.classList.toggle("active",x===b));loadTransactions()};
$("#txApply").onclick=()=>{state.txPage=1;loadTransactions()};$("#txClear").onclick=()=>{$("#txSearch").value="";$("#txStart").value="";$("#txEnd").value="";state.txType="";state.txPage=1;$$("#txTabs button").forEach((x,i)=>x.classList.toggle("active",i===0));loadTransactions()};
$("#txPrev").onclick=()=>{state.txPage--;loadTransactions()};$("#txNext").onclick=()=>{state.txPage++;loadTransactions()};
$("#txBody").onclick=async e=>{const ed=e.target.dataset.edit,del=e.target.dataset.del;if(ed){openTx(txCache.find(x=>x.id===ed));return}if(del&&confirm("Excluir esta transação? Esta ação recalculará os indicadores.")){try{await api("/api/transactions/"+del,{method:"DELETE"});toast("Transação excluída.");loadTransactions();loadDashboard()}catch(err){toast(err.message,false)}}};

function openGoal(g=null){$("#goalForm").reset();$("#goalId").value=g?.id||"";$("#goalModalTitle").textContent=g?"Editar meta":"Nova meta";$("#goalTitle").value=g?.title||"";$("#goalDescription").value=g?.description||"";$("#goalTarget").value=g?(g.target_cents/100).toFixed(2).replace(".",","):"";$("#goalDeadline").value=g?.deadline||"";$("#goalStatus").textContent="";modal("goalModal")}
$("#newGoalBtn").onclick=()=>openGoal();$("#firstGoalBtn").onclick=()=>openGoal();
$("#goalForm").onsubmit=async e=>{e.preventDefault();const id=$("#goalId").value;try{await api(id?"/api/goals/"+id:"/api/goals",{method:id?"PUT":"POST",body:{title:$("#goalTitle").value,description:$("#goalDescription").value||null,target:$("#goalTarget").value,deadline:$("#goalDeadline").value}});modal("goalModal",false);toast(id?"Meta atualizada.":"Meta criada.");loadGoals();loadDashboard()}catch(err){$("#goalStatus").textContent=err.message}};
function amount(gid,kind){state.amountAction={gid,kind};$("#amountTitle").textContent=kind==="reserve"?"Reservar valor":"Retirar reserva";$("#amountValue").value="";$("#amountStatus").textContent="";modal("amountModal")}
$("#amountConfirm").onclick=async()=>{const a=state.amountAction;try{await api(`/api/goals/${a.gid}/${a.kind}`,{method:"POST",body:{amount:$("#amountValue").value}});modal("amountModal",false);toast(a.kind==="reserve"?"Valor reservado.":"Reserva retirada.");loadGoals();loadDashboard()}catch(e){$("#amountStatus").textContent=e.message}};
let goalsCache=[];
async function loadGoals(){
  try{const r=await api("/api/goals");goalsCache=r.items;$("#goalsEmpty").classList.toggle("hidden",r.items.length>0);$("#goalsGrid").innerHTML=r.items.map(g=>{const p=Math.min(100,Math.round((g.reserved_cents/g.target_cents)*100)||0),remaining=Math.max(0,g.target_cents-g.reserved_cents);return`<article class="card goal"><div class="goal-top"><div><h3>${esc(g.title)}</h3><div class="muted">${esc(g.description||"Sem descrição")}</div></div><span class="muted">${brdate(g.deadline)}</span></div><div><div style="display:flex;justify-content:space-between"><b>${money(g.reserved_cents)}</b><span class="muted">de ${money(g.target_cents)}</span></div><div class="progress" style="margin:8px 0"><i style="width:${p}%"></i></div><div class="muted">${p}% concluído • faltam ${money(remaining)}</div></div><div class="goal-actions"><button class="btn small" data-res="${g.id}">Reservar</button><button class="btn small" data-with="${g.id}">Retirar</button><button class="btn small" data-g-edit="${g.id}">Editar</button><button class="btn small" data-complete="${g.id}">Concluir</button><button class="btn small danger" data-g-del="${g.id}">Excluir</button></div></article>`}).join("")}catch(e){toast(e.message,false)}
}
$("#goalsGrid").onclick=async e=>{const d=e.target.dataset;if(d.res)return amount(d.res,"reserve");if(d.with)return amount(d.with,"withdraw");if(d.gEdit)return openGoal(goalsCache.find(x=>x.id===d.gEdit));if(d.complete&&confirm("Concluir a meta sem criar uma despesa?")){await api(`/api/goals/${d.complete}/complete`,{method:"POST"});toast("Meta concluída.");loadGoals();return}if(d.gDel&&confirm("Excluir a meta? As reservas serão liberadas para o saldo disponível sem alterar o saldo total.")){const r=await api(`/api/goals/${d.gDel}`,{method:"DELETE"});toast(r.message);loadGoals();loadDashboard()}};

/* ===== Educação: trilha por níveis + player de aula ===== */
const edu={mods:[],prog:{},pass:70,flat:[],cur:null};
const eduKey=(m,t)=>m+":"+t;
const eduP=(m,t)=>edu.prog[eduKey(m,t)];
const eduDone=(m,t)=>eduP(m,t)?.status==="concluida";
const eduAttempts=p=>{try{return JSON.parse(p?.answers_json||"{}").attempts||0}catch{return 0}};
function eduUnlocked(i){return i===0||eduDone(edu.flat[i-1].m,edu.flat[i-1].t)}


/* Fallback educacional para hospedagem estática (ex.: GitHub Pages).
   Quando o backend responde normalmente, a API continua sendo a fonte principal.
   Sem API, os 4 módulos e o progresso educativo funcionam no navegador. */
const EDU_LOCAL_KEY_PREFIX="fintrack_education_progress_v2:";
function eduLocalKey(){return EDU_LOCAL_KEY_PREFIX+encodeURIComponent(String(state.me?.id||state.me?.email||"guest"))}
const EDU_LOCAL_MODULES=[
  {
    key:"poupanca",level:1,level_name:"Fundamentos",title:"Poupança",description:"Crie o hábito de guardar e entenda a diferença entre poupar, investir e usar a caderneta de poupança.",
    topics:[
      {
        key:"o-que-e-poupanca",title:"O que é Poupança?",goal:"Entender o hábito de poupar e diferenciá-lo de um investimento.",
        explain:"Poupar é separar uma parte do dinheiro de hoje para usar no futuro. Esse hábito pode acontecer em diferentes lugares; a caderneta de poupança é apenas uma das opções para guardar recursos. Investir significa aplicar o dinheiro em um produto com características de risco, liquidez e retorno.",
        example:"Ao receber R$ 200, você decide reservar R$ 20 antes de gastar o restante. Esse ato já é poupar, independentemente de onde os R$ 20 ficarão guardados.",
        acts:[
          {t:"quiz",q:"Qual situação representa melhor o hábito de poupar?",opts:["Gastar tudo e guardar apenas se sobrar","Separar uma parte da renda antes de gastar","Comprar algo parcelado para não mexer no saldo"],answer:1,why:"Poupar começa pela decisão de separar uma parte do dinheiro para objetivos futuros.",right:"Separar uma parte da renda antes de gastar."},
          {t:"multi",q:"Quais afirmações estão corretas?",opts:["Poupar é um hábito financeiro","A caderneta de poupança é uma forma possível de guardar dinheiro","Poupar e investir são exatamente a mesma coisa"],answer:[0,1],why:"Poupar é o hábito; a caderneta é um produto específico. Investir envolve escolher aplicações com características próprias.",right:"Poupar é um hábito e a caderneta é uma das opções para guardar dinheiro."}
        ],
        summary:["Poupar é separar dinheiro para o futuro.","A caderneta de poupança não é sinônimo do hábito de poupar.","Investimentos têm características próprias de risco, liquidez e retorno."],
        sources:[{n:"Banco Central do Brasil",u:"https://www.bcb.gov.br/"},{n:"Portal do Investidor (CVM)",u:"https://www.gov.br/investidor/pt-br"}],reviewed:"2026-10-01"
      },
      {
        key:"vantagens-desvantagens",title:"Vantagens e Desvantagens",goal:"Comparar praticidade, liquidez, risco e retorno ao escolher onde guardar dinheiro.",
        explain:"A escolha de onde guardar depende do objetivo. Para valores que podem ser necessários a qualquer momento, liquidez e segurança pesam mais. Para objetivos mais longos, também vale comparar rendimento, custos e riscos. Nenhuma opção é melhor em todas as situações.",
        example:"Uma reserva para um imprevisto deve ser acessível rapidamente; já um objetivo para daqui a alguns anos permite comparar alternativas com outras condições.",
        acts:[
          {t:"quiz",q:"Para uma reserva que pode ser usada em uma emergência, qual característica costuma ser mais importante?",opts:["Acesso fácil ao dinheiro","Maior oscilação possível","Prazo de resgate muito longo"],answer:0,why:"Uma reserva de emergência precisa estar disponível quando o imprevisto acontece.",right:"Acesso fácil ao dinheiro."},
          {t:"classify",q:"Classifique cada característica.",items:["Pode precisar do dinheiro amanhã","Objetivo para vários anos","Não aceita perder parte do valor"],buckets:["Prioriza liquidez/segurança","Permite comparar prazo/retorno"],answer:[0,1,0],why:"Prazo e tolerância a risco ajudam a escolher a alternativa mais adequada.",right:"Amanhã → liquidez/segurança; vários anos → comparar prazo/retorno; não aceita perda → liquidez/segurança."}
        ],
        summary:["Escolhas financeiras dependem do objetivo e do prazo.","Liquidez indica facilidade de transformar a aplicação em dinheiro disponível.","Compare risco, retorno, custos e regras antes de decidir."],
        sources:[{n:"Portal do Investidor (CVM)",u:"https://www.gov.br/investidor/pt-br"},{n:"Banco Central do Brasil",u:"https://www.bcb.gov.br/"}],reviewed:"2026-10-01"
      },
      {
        key:"dicas-praticas",title:"Dicas Práticas",goal:"Transformar o hábito de guardar em uma rotina sustentável.",
        explain:"Começar pequeno e com regularidade costuma ser mais útil do que esperar sobrar uma grande quantia. Defina um objetivo, escolha um valor realista e automatize ou separe esse valor assim que receber.",
        example:"Guardar R$ 10 toda semana cria constância. Depois, você pode revisar o valor conforme sua realidade mudar.",
        acts:[
          {t:"quiz",q:"Qual estratégia tende a tornar o hábito mais consistente?",opts:["Esperar sobrar no fim do mês","Separar um valor planejado quando o dinheiro entra","Guardar apenas em meses sem nenhuma despesa"],answer:1,why:"Planejar a separação do valor antes dos gastos reduz a dependência do que eventualmente sobra.",right:"Separar um valor planejado quando o dinheiro entra."},
          {t:"calc",q:"Você quer juntar R$ 600 em 6 meses. Desconsiderando rendimentos, quanto precisa guardar por mês?",unit:"R$",answer:100,tolerance:0.01,why:"Divida o valor da meta pelo número de meses: 600 ÷ 6 = 100.",right:"R$ 100 por mês."}
        ],
        summary:["Comece com um valor possível e aumente quando fizer sentido.","Vincule o hábito a um objetivo concreto.","Revise o plano periodicamente."],
        sources:[{n:"Portal do Investidor (CVM)",u:"https://www.gov.br/investidor/pt-br"}],reviewed:"2026-10-01"
      }
    ]
  },
  {
    key:"controle-gastos",level:2,level_name:"Organização",title:"Controle de Gastos",description:"Entenda receitas e despesas, reconheça padrões e organize o orçamento do mês.",
    topics:[
      {
        key:"organizacao-financeira",title:"Organização Financeira",goal:"Classificar entradas e saídas para enxergar o orçamento com clareza.",
        explain:"Receita é dinheiro que entra; despesa é dinheiro que sai. Separar os registros por categoria e período ajuda a entender onde o dinheiro está indo e qual é o resultado do mês.",
        example:"Mesada e pagamento de um trabalho são receitas. Transporte, alimentação e lazer são despesas.",
        acts:[
          {t:"classify",q:"Classifique os itens como receita ou despesa.",items:["Mesada recebida","Passagem de ônibus","Venda de um livro usado","Lanche"],buckets:["Receita","Despesa"],answer:[0,1,0,1],why:"Entradas aumentam os recursos disponíveis; saídas representam gastos.",right:"Mesada e venda → receita; ônibus e lanche → despesa."},
          {t:"quiz",q:"Para que serve registrar gastos por categoria?",opts:["Para entender padrões e planejar melhor","Para impedir qualquer gasto de lazer","Para aumentar automaticamente a renda"],answer:0,why:"Categorias ajudam a visualizar hábitos e apoiar decisões de planejamento.",right:"Entender padrões e planejar melhor."}
        ],
        summary:["Registre receitas e despesas com frequência.","Use categorias para identificar padrões.","Compare entradas e saídas dentro do mesmo período."],
        sources:[{n:"Banco Central do Brasil",u:"https://www.bcb.gov.br/"}],reviewed:"2026-10-01"
      },
      {
        key:"erros-comuns",title:"Erros Comuns",goal:"Reconhecer gastos fixos, variáveis, necessidades, desejos e compras por impulso.",
        explain:"Algumas despesas se repetem com pouca variação; outras mudam mês a mês. Também é útil distinguir necessidades de desejos sem transformar isso em julgamento: a ideia é decidir conscientemente.",
        example:"Uma passagem usada para ir à escola pode ser necessidade; uma compra feita só porque estava em promoção pode ser um desejo ou impulso.",
        acts:[
          {t:"classify",q:"Classifique como gasto mais fixo ou mais variável.",items:["Mensalidade de um curso","Conta de celular com plano fixo","Lanches fora de casa","Passeios"],buckets:["Mais fixo","Mais variável"],answer:[0,0,1,1],why:"Gastos fixos tendem a se repetir com valor semelhante; variáveis mudam mais conforme o uso e as escolhas.",right:"Curso e plano de celular → mais fixos; lanches e passeios → mais variáveis."},
          {t:"quiz",q:"Qual exemplo indica melhor uma compra por impulso?",opts:["Comprar o material escolar já planejado","Comprar um item não planejado só porque apareceu uma promoção","Pagar uma conta prevista no orçamento"],answer:1,why:"Uma compra por impulso costuma acontecer sem planejamento, movida pelo estímulo do momento.",right:"Comprar um item não planejado só por causa da promoção."}
        ],
        summary:["Nem todo gasto variável é desnecessário.","Necessidades e desejos dependem do contexto.","Criar uma pausa antes de compras não planejadas ajuda a reduzir impulsos."],
        sources:[{n:"Banco Central do Brasil",u:"https://www.bcb.gov.br/"}],reviewed:"2026-10-01"
      },
      {
        key:"ferramentas-metodos",title:"Ferramentas e Métodos",goal:"Montar um orçamento fictício que feche em 100%.",
        explain:"Um orçamento distribui a renda entre grupos de gastos e objetivos. Percentuais são referências, não regras rígidas; devem ser adaptados à realidade de cada pessoa.",
        example:"Uma divisão como 50% necessidades, 30% desejos e 20% para objetivos pode servir apenas como ponto de partida para reflexão.",
        acts:[
          {t:"budget",q:"Distribua a renda fictícia usando a referência 50/30/20.",total:"R$ 1.000",cats:["Necessidades","Desejos","Guardar / objetivos"],answer:[50,30,20],why:"A atividade usa 50/30/20 apenas como exemplo de distribuição. Na vida real, ajuste os percentuais à sua realidade.",right:"50% necessidades, 30% desejos e 20% para guardar/objetivos."},
          {t:"calc",q:"Em uma renda fictícia de R$ 1.000, quanto representam 20%?",unit:"R$",answer:200,tolerance:0.01,why:"20% de 1.000 = 0,20 × 1.000 = 200.",right:"R$ 200."}
        ],
        summary:["Orçamento é uma ferramenta de decisão, não uma punição.","Percentuais de referência precisam ser adaptados.","O total das categorias deve ser coerente com a renda disponível."],
        sources:[{n:"Portal do Investidor (CVM)",u:"https://www.gov.br/investidor/pt-br"}],reviewed:"2026-10-01"
      }
    ]
  },
  {
    key:"planejamento",level:3,level_name:"Planejamento",title:"Planejamento Financeiro",description:"Transforme objetivos em metas com valor, prazo e revisões periódicas.",
    topics:[
      {
        key:"definindo-metas",title:"Definindo Metas",goal:"Criar metas específicas, mensuráveis e com prazo.",
        explain:"Uma meta financeira funciona melhor quando você sabe o que quer, quanto custa, quanto já tem e até quando pretende chegar lá. Dividir o valor restante pelo tempo disponível ajuda a estimar um esforço mensal.",
        example:"Notebook de R$ 3.000, com R$ 900 já guardados e prazo de 7 meses: faltam R$ 2.100; sem considerar rendimentos, seriam R$ 300 por mês.",
        acts:[
          {t:"calc",q:"Uma meta custa R$ 3.000 e você já tem R$ 900. Quanto falta?",unit:"R$",answer:2100,tolerance:0.01,why:"Valor restante = 3.000 − 900 = 2.100.",right:"R$ 2.100."},
          {t:"quiz",q:"Qual meta está melhor definida?",opts:["Quero economizar mais algum dia","Quero juntar R$ 1.200 em 12 meses para um curso","Quero gastar menos sem acompanhar nada"],answer:1,why:"Ela tem objetivo, valor e prazo, o que permite acompanhar o progresso.",right:"Juntar R$ 1.200 em 12 meses para um curso."}
        ],
        summary:["Defina objetivo, valor e prazo.","Calcule quanto falta antes de estimar o esforço periódico.","Metas podem ser ajustadas quando a realidade mudar."],
        sources:[{n:"Portal do Investidor (CVM)",u:"https://www.gov.br/investidor/pt-br"}],reviewed:"2026-10-01"
      },
      {
        key:"montando-plano",title:"Montando seu Plano",goal:"Organizar prioridades e revisar o planejamento ao longo do tempo.",
        explain:"Um plano financeiro conecta receitas, despesas e metas. Revisar o plano ajuda a perceber mudanças na renda, nos preços e nas prioridades. A regra 50/30/20 pode ser uma referência inicial, nunca uma obrigação.",
        example:"Se sua renda diminuir em um mês, você pode reduzir temporariamente a parcela de um objetivo e retomar quando for possível, em vez de abandonar o plano.",
        acts:[
          {t:"multi",q:"Quais ações fazem parte de uma boa revisão do planejamento?",opts:["Comparar o planejado com o realizado","Atualizar prazos e valores quando necessário","Ignorar mudanças de renda e manter tudo igual"],answer:[0,1],why:"Planejamento precisa acompanhar a realidade; comparar resultados e ajustar metas é parte do processo.",right:"Comparar planejado x realizado e atualizar prazos/valores quando necessário."},
          {t:"quiz",q:"A regra 50/30/20 deve ser tratada como:",opts:["Uma lei financeira obrigatória","Um exemplo adaptável de organização","Uma garantia de que sempre sobrará dinheiro"],answer:1,why:"Ela é apenas uma referência de distribuição e precisa ser adaptada à realidade de cada pessoa.",right:"Um exemplo adaptável de organização."}
        ],
        summary:["Planejamento deve ser revisado periodicamente.","Referências de orçamento precisam ser adaptadas.","Mudanças de rota fazem parte de um plano realista."],
        sources:[{n:"Portal do Investidor (CVM)",u:"https://www.gov.br/investidor/pt-br"}],reviewed:"2026-10-01"
      }
    ]
  },
  {
    key:"investimentos",level:4,level_name:"Primeiros investimentos",title:"Investimentos",description:"Aprenda conceitos básicos de juros, inflação, Selic, liquidez, risco e produtos comuns.",
    topics:[
      {
        key:"tesouro-direto",title:"Tesouro Direto",goal:"Entender o que é o Tesouro Direto e por que prazo e preço importam.",
        explain:"Tesouro Direto é o programa de venda de títulos públicos federais para pessoas físicas. Os títulos têm regras diferentes de remuneração e vencimento, e o valor de venda antes do vencimento pode variar conforme as condições de mercado.",
        example:"Uma pessoa pode comprar um título para um objetivo futuro, mas deve observar vencimento, liquidez, tributação e possibilidade de oscilação do preço.",
        acts:[
          {t:"quiz",q:"O que você compra no Tesouro Direto?",opts:["Uma ação de qualquer empresa","Um título público federal","Uma moeda estrangeira física"],answer:1,why:"O Tesouro Direto é o programa de venda de títulos públicos federais para pessoas físicas.",right:"Um título público federal."},
          {t:"multi",q:"Antes de investir, quais pontos devem ser observados?",opts:["Prazo e vencimento","Liquidez e riscos","A promessa de lucro garantido"],answer:[0,1],why:"Investimentos não têm lucro garantido; é importante entender prazo, liquidez, riscos, custos e tributação.",right:"Prazo/vencimento e liquidez/riscos."}
        ],
        summary:["Tesouro Direto dá acesso a títulos públicos federais.","Cada título tem regras próprias.","Venda antes do vencimento pode envolver oscilação de preço."],
        sources:[{n:"Tesouro Direto",u:"https://www.tesourodireto.com.br/"},{n:"Portal do Investidor (CVM)",u:"https://www.gov.br/investidor/pt-br"}],reviewed:"2026-10-01"
      },
      {
        key:"taxa-selic",title:"Taxa Selic",goal:"Entender o papel da Selic sem decorar uma taxa que muda ao longo do tempo.",
        explain:"A Selic é a taxa básica de juros da economia brasileira. Ela influencia outras taxas de juros e as condições financeiras. Seu valor muda ao longo do tempo, por isso deve ser consultado em fonte oficial quando necessário.",
        example:"Quando você vê uma notícia sobre mudança da Selic, isso pode influenciar o custo de crédito e a remuneração de alguns investimentos, mas o efeito específico depende do produto.",
        acts:[
          {t:"quiz",q:"Qual é a melhor forma de verificar a Selic atual?",opts:["Usar um número antigo memorizado","Consultar uma fonte oficial atualizada","Assumir que ela nunca muda"],answer:1,why:"A Selic é definida periodicamente e pode mudar; por isso, a fonte oficial é a referência correta.",right:"Consultar uma fonte oficial atualizada."},
          {t:"quiz",q:"A Selic é:",opts:["A taxa básica de juros da economia brasileira","Um tipo de ação","Uma garantia de rendimento para qualquer investimento"],answer:0,why:"A Selic é a taxa básica de juros; produtos financeiros podem reagir a ela de formas diferentes.",right:"A taxa básica de juros da economia brasileira."}
        ],
        summary:["A Selic é a taxa básica de juros.","Seu valor muda ao longo do tempo.","Consulte o Banco Central para dados atuais."],
        sources:[{n:"Banco Central do Brasil",u:"https://www.bcb.gov.br/controleinflacao/taxaselic"}],reviewed:"2026-10-01"
      },
      {
        key:"fundos-imobiliarios",title:"Fundos Imobiliários",goal:"Conhecer a ideia geral de fundos imobiliários, renda e riscos.",
        explain:"Fundos de investimento imobiliário (FIIs) reúnem recursos de investidores para aplicações ligadas ao mercado imobiliário. As cotas podem oscilar, rendimentos não são garantidos e os riscos variam conforme a estratégia do fundo.",
        example:"Um fundo pode investir em imóveis ou ativos ligados ao setor. O investidor compra cotas e deve analisar carteira, riscos, liquidez, custos e documentos do fundo.",
        acts:[
          {t:"quiz",q:"Sobre fundos imobiliários, qual afirmação é correta?",opts:["O rendimento é sempre garantido","As cotas podem oscilar e existem riscos","Eles não precisam divulgar informações"],answer:1,why:"FIIs são investimentos sujeitos a riscos e oscilação de preço; rendimentos não são garantidos.",right:"As cotas podem oscilar e existem riscos."},
          {t:"multi",q:"O que vale observar antes de investir em um FII?",opts:["Carteira e estratégia","Liquidez, riscos e custos","Apenas o rendimento do último mês"],answer:[0,1],why:"Uma análise deve considerar vários fatores, não apenas um rendimento recente.",right:"Carteira/estratégia e liquidez/riscos/custos."}
        ],
        summary:["FIIs são investimentos coletivos ligados ao mercado imobiliário.","Cotas e rendimentos podem variar.","Leia documentos e entenda riscos antes de decidir."],
        sources:[{n:"Portal do Investidor (CVM)",u:"https://www.gov.br/investidor/pt-br"}],reviewed:"2026-10-01"
      },
      {
        key:"outros-investimentos",title:"Outros Investimentos Básicos",goal:"Comparar conceitos de CDB, inflação, liquidez, risco e retorno.",
        explain:"CDBs são títulos emitidos por bancos e podem ter regras diferentes de remuneração, prazo e liquidez. Em qualquer investimento, compare o retorno esperado com inflação, riscos, custos, impostos e o momento em que você pode precisar do dinheiro.",
        example:"Dois investimentos podem mostrar taxas diferentes, mas um pode ter prazo maior ou liquidez menor. Comparar apenas um número pode levar a uma decisão inadequada.",
        acts:[
          {t:"classify",q:"Associe cada conceito à ideia mais próxima.",items:["Liquidez","Inflação","Risco"],buckets:["Facilidade de resgatar/usar o dinheiro","Perda de poder de compra ao longo do tempo","Possibilidade de resultado diferente do esperado"],answer:[0,1,2],why:"Esses três conceitos ajudam a comparar investimentos com objetivos e prazos diferentes.",right:"Liquidez → acesso ao dinheiro; inflação → poder de compra; risco → incerteza do resultado."},
          {t:"quiz",q:"Qual comparação é mais completa ao avaliar um investimento?",opts:["Olhar apenas a maior taxa anunciada","Considerar retorno, risco, liquidez, prazo, custos e impostos","Escolher o produto que um amigo usou"],answer:1,why:"Uma decisão adequada considera o conjunto de características e o objetivo do investidor.",right:"Considerar retorno, risco, liquidez, prazo, custos e impostos."}
        ],
        summary:["Retorno deve ser analisado junto com risco e liquidez.","Inflação afeta o poder de compra.","Produtos de renda fixa podem ter regras de prazo, resgate, impostos e garantias diferentes."],
        sources:[{n:"Banco Central do Brasil",u:"https://www.bcb.gov.br/"},{n:"Portal do Investidor (CVM)",u:"https://www.gov.br/investidor/pt-br"}],reviewed:"2026-10-01"
      }
    ]
  }
];

const EDU_EXTRA_ACTIVITIES={
  "poupanca:o-que-e-poupanca":[
    {t:"calc",q:"Você recebe R$ 400 e decide poupar 15%. Quanto separa?",unit:"R$",answer:60,tolerance:.01,why:"15% de 400 é 0,15 × 400 = 60.",right:"R$ 60."},
    {t:"quiz",q:"Qual atitude transforma poupar em um hábito?",opts:["Separar um valor com frequência","Guardar somente quando sobrar muito","Mudar de objetivo toda semana"],answer:0,why:"A regularidade ajuda a tornar o hábito previsível e sustentável.",right:"Separar um valor com frequência."}
  ],
  "poupanca:vantagens-desvantagens":[
    {t:"multi",q:"Para dinheiro que pode ser necessário em breve, o que merece atenção?",opts:["Liquidez","Segurança compatível com o objetivo","Apenas a maior promessa de retorno"],answer:[0,1],why:"Prazo curto aumenta a importância de acesso e segurança; retorno não deve ser analisado isoladamente.",right:"Liquidez e segurança compatível com o objetivo."},
    {t:"calc",q:"Se você separar 5% de R$ 1.000, quanto guardará?",unit:"R$",answer:50,tolerance:.01,why:"5% de 1.000 = 50.",right:"R$ 50."}
  ],
  "poupanca:dicas-praticas":[
    {t:"classify",q:"Classifique os hábitos.",items:["Separar o valor ao receber","Esperar o fim do mês para ver se sobra","Definir uma meta com prazo","Usar a reserva para compras por impulso"],buckets:["Ajuda a poupar","Atrapalha o hábito"],answer:[0,1,0,1],why:"Planejamento, objetivo e constância favorecem o hábito; depender de sobras e usar a reserva sem necessidade atrapalham.",right:"Separar e definir meta ajudam; esperar sobrar e gastar a reserva por impulso atrapalham."},
    {t:"quiz",q:"Se o valor planejado para poupar ficou pesado, qual atitude é mais sustentável?",opts:["Abandonar a meta","Ajustar o valor e manter a regularidade","Fazer dívida para continuar poupando"],answer:1,why:"Um valor realista pode ser mantido por mais tempo e revisado depois.",right:"Ajustar o valor e manter a regularidade."}
  ],
  "controle-gastos:organizacao-financeira":[
    {t:"calc",q:"Você recebeu R$ 900 e gastou R$ 550. Qual foi o resultado do período?",unit:"R$",answer:350,tolerance:.01,why:"Resultado = receitas − despesas = 900 − 550.",right:"R$ 350."},
    {t:"multi",q:"Quais informações deixam um lançamento financeiro mais útil?",opts:["Valor e data","Categoria e descrição","A cor do celular usado no cadastro"],answer:[0,1],why:"Valor, data, categoria e descrição ajudam a entender e filtrar o histórico.",right:"Valor/data e categoria/descrição."}
  ],
  "controle-gastos:erros-comuns":[
    {t:"multi",q:"Quais atitudes ajudam a reduzir compras por impulso?",opts:["Criar um tempo de espera","Comparar com o orçamento","Comprar porque a promoção termina hoje"],answer:[0,1],why:"Pausa e comparação com o plano ajudam a decidir com mais consciência.",right:"Criar tempo de espera e comparar com o orçamento."},
    {t:"calc",q:"Três assinaturas custam R$ 18, R$ 25 e R$ 37 por mês. Quanto elas somam?",unit:"R$",answer:80,tolerance:.01,why:"18 + 25 + 37 = 80.",right:"R$ 80 por mês."}
  ],
  "controle-gastos:ferramentas-metodos":[
    {t:"quiz",q:"Um orçamento que funcionou no mês passado precisa ser idêntico neste mês?",opts:["Sim, sempre","Não; ele pode ser ajustado à realidade","Somente se houver despesas"],answer:1,why:"Orçamento é uma ferramenta adaptável e deve acompanhar mudanças de renda e gastos.",right:"Não; ele pode ser ajustado à realidade."},
    {t:"classify",q:"Classifique os exemplos.",items:["Aluguel com valor semelhante todo mês","Lazer que muda mês a mês","Plano mensal de internet","Presentes ocasionais"],buckets:["Mais previsível","Mais variável"],answer:[0,1,0,1],why:"Alguns gastos têm frequência e valores mais previsíveis; outros dependem das escolhas do período.",right:"Aluguel/internet → previsíveis; lazer/presentes → variáveis."}
  ],
  "planejamento:definindo-metas":[
    {t:"calc",q:"Uma meta custa R$ 2.400, você já tem R$ 600 e faltam 6 meses. Sem considerar rendimentos, quanto precisa guardar por mês?",unit:"R$",answer:300,tolerance:.01,why:"Faltam 1.800; 1.800 ÷ 6 = 300.",right:"R$ 300 por mês."},
    {t:"multi",q:"O que deixa uma meta mais fácil de acompanhar?",opts:["Valor definido","Prazo","Objetivo claro","Apenas vontade de economizar"],answer:[0,1,2],why:"Objetivo, valor e prazo permitem medir o progresso.",right:"Objetivo claro, valor definido e prazo."}
  ],
  "planejamento:montando-plano":[
    {t:"classify",q:"Em uma revisão do plano, classifique as ações.",items:["Atualizar um gasto que aumentou","Ignorar uma queda de renda","Recalcular o valor mensal da meta","Comparar planejado e realizado"],buckets:["Revisão útil","Evitar"],answer:[0,1,0,0],why:"Um bom plano acompanha a realidade e usa dados para ajustar decisões.",right:"Atualizar, recalcular e comparar ajudam; ignorar a renda deve ser evitado."},
    {t:"calc",q:"Se você decide direcionar 10% de R$ 1.800 para uma meta, qual é o valor?",unit:"R$",answer:180,tolerance:.01,why:"10% de 1.800 = 180.",right:"R$ 180."}
  ],
  "investimentos:tesouro-direto":[
    {t:"quiz",q:"Vender um título antes do vencimento pode gerar um valor diferente do esperado no vencimento?",opts:["Sim","Não, o preço nunca muda","Somente em fins de semana"],answer:0,why:"O preço de venda antes do vencimento pode oscilar conforme as condições de mercado.",right:"Sim."},
    {t:"multi",q:"Quais pontos devem ser comparados em um título?",opts:["Vencimento","Liquidez","Forma de remuneração","Apenas o nome do produto"],answer:[0,1,2],why:"Prazo, liquidez e remuneração fazem parte das características relevantes.",right:"Vencimento, liquidez e forma de remuneração."}
  ],
  "investimentos:taxa-selic":[
    {t:"multi",q:"Uma mudança na Selic pode influenciar:",opts:["Condições de crédito","Remuneração de alguns investimentos","A cor das cédulas"],answer:[0,1],why:"A taxa básica influencia condições financeiras e vários juros da economia.",right:"Crédito e remuneração de alguns investimentos."},
    {t:"classify",q:"Classifique as formas de obter informação.",items:["Site oficial do Banco Central","Print antigo sem data","Comunicado atualizado do Copom","Mensagem encaminhada sem fonte"],buckets:["Fonte mais confiável","Exige verificação"],answer:[0,1,0,1],why:"Dados financeiros que mudam devem ser conferidos em fontes oficiais e atualizadas.",right:"BCB/Copom → mais confiáveis; print/mensagem sem fonte → exigem verificação."}
  ],
  "investimentos:fundos-imobiliarios":[
    {t:"quiz",q:"Usar apenas o rendimento do último mês é suficiente para avaliar um FII?",opts:["Sim","Não","Somente se a cota subir"],answer:1,why:"Uma análise precisa considerar carteira, riscos, liquidez, custos e documentos, não só um mês.",right:"Não."},
    {t:"multi",q:"Quais riscos podem existir em FIIs?",opts:["Oscilação do preço das cotas","Mudanças nos rendimentos","Vacância ou risco dos ativos","Rendimento garantido por definição"],answer:[0,1,2],why:"Preço e rendimentos podem variar, e os ativos do fundo têm riscos próprios.",right:"Oscilação, variação de rendimentos e riscos dos ativos."}
  ],
  "investimentos:outros-investimentos":[
    {t:"classify",q:"Associe o foco principal de cada pergunta.",items:["Quando posso resgatar?","Posso perder dinheiro?","Quanto custa investir?","O retorno acompanha algum índice?"],buckets:["Liquidez","Risco","Custos","Rentabilidade"],answer:[0,1,2,3],why:"Essas perguntas ajudam a comparar produtos por dimensões diferentes.",right:"Resgate → liquidez; perda → risco; custo → custos; índice → rentabilidade."},
    {t:"quiz",q:"Por que comparar retorno nominal com inflação pode ser importante?",opts:["Porque inflação afeta o poder de compra","Porque elimina todo risco","Porque garante lucro"],answer:0,why:"O ganho nominal não mostra sozinho a variação do poder de compra.",right:"Porque a inflação afeta o poder de compra."}
  ]
};

Object.entries(EDU_EXTRA_ACTIVITIES).forEach(([key,acts])=>{
  const [mk,tk]=key.split(":");
  const mod=EDU_LOCAL_MODULES.find(m=>m.key===mk),topic=mod?.topics.find(t=>t.key===tk);
  if(topic)topic.acts.push(...acts);
});

const EDU_EXTRA_TOPICS={
  poupanca:[
    {key:"reserva-emergencia",title:"Reserva para Imprevistos",goal:"Planejar uma reserva para despesas inesperadas sem depender de crédito.",
      explain:"Uma reserva para imprevistos serve como proteção para situações não planejadas. O tamanho adequado depende da realidade da pessoa; o ponto central é construir aos poucos e manter o dinheiro acessível para quando for necessário.",
      example:"Se um conserto inesperado custa R$ 300, ter uma reserva evita que esse valor precise virar uma dívida.",
      acts:[
        {t:"quiz",q:"Qual é a principal função de uma reserva para imprevistos?",opts:["Financiar compras por impulso","Ajudar a enfrentar despesas inesperadas","Garantir rendimento alto"],answer:1,why:"A reserva reduz a necessidade de recorrer a dívida quando aparece uma despesa inesperada.",right:"Ajudar a enfrentar despesas inesperadas."},
        {t:"calc",q:"Você quer formar R$ 1.200 em 12 meses. Sem considerar rendimentos, quanto separa por mês?",unit:"R$",answer:100,tolerance:.01,why:"1.200 ÷ 12 = 100.",right:"R$ 100 por mês."},
        {t:"multi",q:"Quais características combinam com uma reserva para imprevistos?",opts:["Acesso relativamente fácil","Risco compatível com a necessidade de preservar o valor","Prazo que impede qualquer resgate por anos"],answer:[0,1],why:"A reserva precisa estar disponível e ter risco compatível com sua função de proteção.",right:"Acesso fácil e risco compatível."},
        {t:"classify",q:"Classifique o uso.",items:["Remédio inesperado","Viagem de lazer planejada","Conserto urgente","Compra de roupa por impulso"],buckets:["Pode ser imprevisto","Melhor planejar à parte"],answer:[0,1,0,1],why:"Reserva é voltada a imprevistos; objetivos e desejos previsíveis podem ter metas próprias.",right:"Remédio/conserto → imprevistos; viagem/roupa → planejar à parte."}
      ],summary:["Construa a reserva gradualmente.","Priorize acesso e segurança compatíveis com o objetivo.","Use-a para imprevistos e depois recomponha."],
      sources:[{n:"Portal do Investidor (CVM)",u:"https://www.gov.br/investidor/pt-br"}],reviewed:"2026-10-02"},
    {key:"automatizando-poupanca",title:"Automatizando o Hábito",goal:"Criar gatilhos simples para poupar com regularidade.",
      explain:"Automatizar ou programar a separação de um valor logo após receber reduz a chance de gastar primeiro e tentar guardar apenas o que sobrar.",
      example:"No dia seguinte ao recebimento, você transfere automaticamente R$ 40 para a meta escolhida.",
      acts:[
        {t:"quiz",q:"Qual momento tende a facilitar a separação do valor planejado?",opts:["Logo após receber","Somente depois de todos os desejos do mês","Quando aparecer uma promoção"],answer:0,why:"Separar cedo dá prioridade ao objetivo financeiro.",right:"Logo após receber."},
        {t:"calc",q:"Guardando R$ 40 por semana durante 10 semanas, quanto você acumula sem considerar rendimentos?",unit:"R$",answer:400,tolerance:.01,why:"40 × 10 = 400.",right:"R$ 400."},
        {t:"multi",q:"Quais gatilhos podem ajudar na constância?",opts:["Transferência programada","Lembrete no dia do recebimento","Esperar lembrar espontaneamente todo mês"],answer:[0,1],why:"Automação e lembretes reduzem a dependência da memória.",right:"Transferência programada e lembrete."},
        {t:"classify",q:"Classifique.",items:["Valor pequeno que cabe no orçamento","Valor tão alto que exige dívida","Revisar o valor após mudança de renda","Cancelar o hábito depois de um mês difícil"],buckets:["Sustentável","Precisa de ajuste"],answer:[0,1,0,1],why:"O hábito funciona melhor quando o valor é realista e pode ser revisado.",right:"Valor possível/revisão → sustentável; dívida/cancelamento → precisa ajuste."}
      ],summary:["Automação reduz esquecimentos.","Comece com valor realista.","Revise a quantia quando a renda mudar."],
      sources:[{n:"Portal do Investidor (CVM)",u:"https://www.gov.br/investidor/pt-br"}],reviewed:"2026-10-02"}
  ],
  "controle-gastos":[
    {key:"gastos-invisiveis",title:"Pequenos Gastos e Assinaturas",goal:"Perceber como valores pequenos e recorrentes afetam o total do mês.",
      explain:"Pequenos gastos isolados podem parecer irrelevantes, mas a soma mensal pode ser importante. Assinaturas recorrentes também merecem revisão para verificar se continuam sendo usadas.",
      example:"R$ 8 gastos quatro vezes por semana representam R$ 32 por semana e podem passar de R$ 100 no mês.",
      acts:[
        {t:"calc",q:"Um gasto de R$ 8 acontece 4 vezes por semana. Quanto soma em 4 semanas?",unit:"R$",answer:128,tolerance:.01,why:"8 × 4 × 4 = 128.",right:"R$ 128."},
        {t:"quiz",q:"Qual é a melhor razão para revisar assinaturas?",opts:["Descobrir serviços que não são mais úteis","Cancelar tudo automaticamente","Aumentar a quantidade de cobranças"],answer:0,why:"A revisão ajuda a decidir conscientemente o que ainda faz sentido.",right:"Descobrir serviços que não são mais úteis."},
        {t:"multi",q:"O que ajuda a enxergar pequenos gastos?",opts:["Registrar com frequência","Agrupar por categoria","Ignorar valores abaixo de R$ 10"],answer:[0,1],why:"Registro e categorização mostram o efeito acumulado.",right:"Registrar e agrupar por categoria."},
        {t:"classify",q:"Classifique.",items:["Streaming usado toda semana","Assinatura esquecida há meses","Aplicativo necessário para estudo","Serviço duplicado"],buckets:["Revisar com contexto","Forte candidato a corte"],answer:[0,1,0,1],why:"Uso e finalidade importam; itens esquecidos ou duplicados merecem atenção.",right:"Usados/necessários → revisar com contexto; esquecidos/duplicados → candidatos a corte."}
      ],summary:["Some valores pequenos.","Revise recorrências.","Decida com base em uso e prioridade."],
      sources:[{n:"Banco Central do Brasil",u:"https://www.bcb.gov.br/"}],reviewed:"2026-10-02"},
    {key:"fechamento-mensal",title:"Fechamento do Mês",goal:"Comparar receitas, despesas e resultado para aprender com o período.",
      explain:"Fechar o mês significa revisar o que entrou, o que saiu e o que foi diferente do planejado. O objetivo não é julgar, mas entender padrões e melhorar o próximo planejamento.",
      example:"Se alimentação ficou acima do previsto, você pode investigar se houve aumento de preços, mais refeições fora ou um orçamento inicial irrealista.",
      acts:[
        {t:"calc",q:"Receitas de R$ 1.500 e despesas de R$ 1.280 geram qual resultado?",unit:"R$",answer:220,tolerance:.01,why:"1.500 − 1.280 = 220.",right:"R$ 220."},
        {t:"quiz",q:"Um mês com resultado negativo significa necessariamente que todo gasto foi errado?",opts:["Sim","Não; é preciso analisar o contexto","Sim, se houve lazer"],answer:1,why:"Imprevistos, variações e decisões planejadas precisam ser analisados antes de concluir.",right:"Não; é preciso analisar o contexto."},
        {t:"multi",q:"O que revisar no fechamento?",opts:["Categorias acima do previsto","Receitas que mudaram","Metas e reservas","Somente o saldo final"],answer:[0,1,2],why:"O saldo final é importante, mas entender as causas gera aprendizado.",right:"Categorias, receitas e metas/reservas."},
        {t:"classify",q:"Classifique.",items:["Comparar com o orçamento","Esconder um gasto para o total parecer melhor","Anotar um imprevisto","Ajustar o próximo mês"],buckets:["Boa prática","Evitar"],answer:[0,1,0,0],why:"Transparência e comparação ajudam o planejamento; esconder dados prejudica.",right:"Comparar/anotar/ajustar → boas práticas; esconder → evitar."}
      ],summary:["Compare planejado e realizado.","Procure causas, não culpa.","Use o aprendizado no mês seguinte."],
      sources:[{n:"Banco Central do Brasil",u:"https://www.bcb.gov.br/"}],reviewed:"2026-10-02"}
  ],
  planejamento:[
    {key:"cenarios-imprevistos",title:"Cenários e Imprevistos",goal:"Criar um plano B para mudanças de renda e despesas inesperadas.",
      explain:"Planejamento fica mais robusto quando considera cenários. Você pode definir quais gastos reduzir primeiro, quanto manter em reserva e como ajustar temporariamente uma meta.",
      example:"Se a renda cair 15%, você já sabe quais despesas variáveis revisar antes de mexer em itens essenciais.",
      acts:[
        {t:"quiz",q:"Para que serve um cenário alternativo?",opts:["Prever o futuro com certeza","Preparar respostas para mudanças possíveis","Eliminar todos os imprevistos"],answer:1,why:"Cenários não preveem com certeza; ajudam a pensar em respostas antes do problema.",right:"Preparar respostas para mudanças possíveis."},
        {t:"calc",q:"Uma renda de R$ 2.000 cai 15%. Qual passa a ser a nova renda?",unit:"R$",answer:1700,tolerance:.01,why:"15% de 2.000 = 300; 2.000 − 300 = 1.700.",right:"R$ 1.700."},
        {t:"multi",q:"Em um mês apertado, quais ações podem fazer sentido?",opts:["Revisar gastos variáveis","Recalcular temporariamente a meta","Ignorar contas essenciais"],answer:[0,1],why:"Ajustes devem preservar prioridades e refletir a nova realidade.",right:"Revisar variáveis e recalcular a meta."},
        {t:"classify",q:"Classifique.",items:["Conta essencial","Passeio opcional","Reserva para imprevisto","Compra não planejada"],buckets:["Prioridade maior","Pode ser adiado/revisto"],answer:[0,1,0,1],why:"Em cenário apertado, itens essenciais e proteção financeira tendem a ter prioridade.",right:"Conta/reserva → prioridade maior; passeio/compra → revisar."}
      ],summary:["Pense em cenários.","Defina prioridades.","Ajuste metas sem abandonar o planejamento."],
      sources:[{n:"Portal do Investidor (CVM)",u:"https://www.gov.br/investidor/pt-br"}],reviewed:"2026-10-02"},
    {key:"credito-dividas",title:"Crédito e Dívidas",goal:"Entender que parcelas, juros e custo total devem entrar no planejamento.",
      explain:"Crédito permite antecipar uma compra, mas cria compromissos futuros. Antes de contratar, compare valor da parcela, quantidade de parcelas, juros, custo total e impacto no orçamento.",
      example:"Uma parcela que parece pequena pode ocupar parte da renda durante muitos meses; por isso, o custo total e o prazo importam.",
      acts:[
        {t:"quiz",q:"Antes de assumir uma dívida, o que deve ser analisado além da parcela?",opts:["Custo total e prazo","Apenas a propaganda","Somente o primeiro pagamento"],answer:0,why:"Prazo, juros e custo total mostram o compromisso completo.",right:"Custo total e prazo."},
        {t:"calc",q:"Uma compra tem 8 parcelas de R$ 75. Qual é o total pago, sem outras cobranças?",unit:"R$",answer:600,tolerance:.01,why:"8 × 75 = 600.",right:"R$ 600."},
        {t:"multi",q:"Quais sinais indicam que uma parcela pode pesar no orçamento?",opts:["Já existem muitas parcelas ativas","A renda varia e não há margem","A parcela cabe com folga em todos os cenários"],answer:[0,1],why:"Muitos compromissos e pouca margem aumentam o risco de dificuldade.",right:"Muitas parcelas e renda sem margem."},
        {t:"classify",q:"Classifique.",items:["Comparar propostas","Olhar o custo total","Contratar sem ler condições","Contar com renda incerta como garantida"],buckets:["Boa prática","Risco maior"],answer:[0,0,1,1],why:"Comparação e leitura reduzem surpresas; assumir certezas sem base aumenta o risco.",right:"Comparar/custo total → boas práticas; contratar sem ler/renda incerta → risco maior."}
      ],summary:["Parcela não é o único número importante.","Compare custo total e prazo.","Inclua dívidas no orçamento futuro."],
      sources:[{n:"Banco Central do Brasil",u:"https://www.bcb.gov.br/"}],reviewed:"2026-10-02"}
  ],
  investimentos:[
    {key:"risco-liquidez-diversificacao",title:"Risco, Liquidez e Diversificação",goal:"Comparar investimentos por mais de uma característica.",
      explain:"Investimentos diferem em risco, liquidez, prazo e forma de retorno. Diversificação significa distribuir recursos entre exposições diferentes; ela pode reduzir concentração, mas não elimina riscos.",
      example:"Manter todo o dinheiro em um único ativo concentra a exposição. Distribuir conforme objetivos e perfil pode reduzir a dependência de um único resultado.",
      acts:[
        {t:"quiz",q:"Diversificação elimina todo risco?",opts:["Sim","Não","Somente em renda fixa"],answer:1,why:"Diversificação reduz concentração, mas nenhum investimento fica livre de todos os riscos.",right:"Não."},
        {t:"multi",q:"O que comparar entre investimentos?",opts:["Risco","Liquidez","Prazo","Retorno esperado"],answer:[0,1,2,3],why:"A decisão depende de várias dimensões e do objetivo.",right:"Risco, liquidez, prazo e retorno esperado."},
        {t:"classify",q:"Associe a pergunta.",items:["Posso precisar do dinheiro amanhã","Aceito oscilações maiores","Objetivo é para muitos anos","Quero evitar concentração"],buckets:["Liquidez","Risco","Prazo","Diversificação"],answer:[0,1,2,3],why:"Cada pergunta destaca uma dimensão diferente.",right:"Amanhã → liquidez; oscilações → risco; anos → prazo; concentração → diversificação."},
        {t:"quiz",q:"Um investimento com retorno potencial maior deve ser escolhido automaticamente?",opts:["Sim","Não; é preciso comparar riscos e objetivo","Sim, se for popular"],answer:1,why:"Retorno potencial não deve ser analisado isoladamente.",right:"Não; compare riscos e objetivo."}
      ],summary:["Compare várias dimensões.","Diversifique de forma coerente com objetivos.","Retorno potencial não substitui análise de risco."],
      sources:[{n:"Portal do Investidor (CVM)",u:"https://www.gov.br/investidor/pt-br"}],reviewed:"2026-10-02"},
    {key:"golpes-promessas",title:"Golpes e Promessas de Retorno",goal:"Reconhecer sinais de alerta antes de enviar dinheiro ou dados.",
      explain:"Promessas de retorno alto, rápido e garantido, pressão para decidir imediatamente e falta de informações verificáveis são sinais de alerta. Antes de investir, pesquise a instituição e consulte fontes oficiais.",
      example:"Uma mensagem diz que você precisa transferir dinheiro em dez minutos para garantir lucro certo. A pressa e a garantia de ganho são sinais para interromper e verificar.",
      acts:[
        {t:"multi",q:"Quais são sinais de alerta?",opts:["Lucro alto garantido","Pressão para decidir imediatamente","Informações claras e verificáveis em fonte oficial"],answer:[0,1],why:"Garantia de lucro e pressão são sinais comuns de abordagem arriscada.",right:"Lucro garantido e pressão imediata."},
        {t:"quiz",q:"Recebeu uma oferta de investimento desconhecida. Qual é o primeiro passo mais prudente?",opts:["Transferir pouco para testar","Verificar instituição e informações em fontes oficiais","Compartilhar senha para agilizar cadastro"],answer:1,why:"Verificação vem antes de qualquer envio de dinheiro ou credencial.",right:"Verificar em fontes oficiais."},
        {t:"classify",q:"Classifique.",items:["Site oficial do regulador","Pedido de senha bancária por mensagem","Contrato com informações verificáveis","Promessa de dobrar o dinheiro sem risco"],buckets:["Ajuda a verificar","Sinal de alerta"],answer:[0,1,0,1],why:"Fontes oficiais e documentos verificáveis ajudam; senhas e lucro sem risco são alertas.",right:"Fonte/contrato → verificar; senha/promessa → alerta."},
        {t:"quiz",q:"É seguro compartilhar senha bancária para liberar um investimento?",opts:["Sim","Não","Somente se a pessoa parecer confiável"],answer:1,why:"Senhas são credenciais pessoais e não devem ser compartilhadas.",right:"Não."}
      ],summary:["Desconfie de garantias irreais.","Não compartilhe senhas.","Verifique instituições e ofertas em fontes oficiais."],
      sources:[{n:"Portal do Investidor (CVM)",u:"https://www.gov.br/investidor/pt-br"}],reviewed:"2026-10-02"}
  ]
};
Object.entries(EDU_EXTRA_TOPICS).forEach(([mk,topics])=>{
  const mod=EDU_LOCAL_MODULES.find(m=>m.key===mk);if(mod)mod.topics.push(...topics);
});

function localEduProgress(){
  try{
    const key=eduLocalKey(),current=localStorage.getItem(key);
    if(current)return JSON.parse(current)||{};
    const legacy=localStorage.getItem("fintrack_education_progress_v1");
    if(legacy){localStorage.setItem(key,legacy);return JSON.parse(legacy)||{}}
    const d=localData();if(d.education&&Object.keys(d.education).length)return d.education;
    return {}
  }catch{return {}}
}
function saveLocalEduProgress(){
  try{localStorage.setItem(eduLocalKey(),JSON.stringify(edu.prog));const d=localData();d.education=edu.prog;saveLocalData(d)}catch{}
}
function setLocalEducation(){
  edu.local=true;
  edu.mods=EDU_LOCAL_MODULES;
  edu.pass=70;
  edu.prog=localEduProgress();
  edu.flat=[];
  EDU_LOCAL_MODULES.forEach(m=>m.topics.forEach(t=>edu.flat.push({m:m.key,t:t.key,mod:m,topic:t})));
}
function sameArray(a,b){return Array.isArray(a)&&Array.isArray(b)&&a.length===b.length&&a.every((v,i)=>v===b[i])}
function localCheckActivity(a,answer){
  let ok=false,fraction=0;
  if(a.t==="quiz"){ok=Number(answer)===Number(a.answer);fraction=ok?1:0}
  else if(a.t==="calc"){const v=Number(String(answer).replace(",",".")),target=Number(a.answer),tol=Number(a.tolerance??0.01);ok=Number.isFinite(v)&&Math.abs(v-target)<=tol;fraction=ok?1:0}
  else if(a.t==="multi"){
    const got=(answer||[]).map(Number).sort((x,y)=>x-y),exp=(a.answer||[]).map(Number).sort((x,y)=>x-y);
    ok=sameArray(got,exp);
    const hit=got.filter(x=>exp.includes(x)).length,wrong=got.filter(x=>!exp.includes(x)).length;
    fraction=Math.max(0,Math.min(1,(hit-wrong)/Math.max(1,exp.length)));
  }else if(a.t==="classify"){
    const got=(answer||[]).map(Number),exp=(a.answer||[]).map(Number);
    const hit=exp.reduce((s,x,i)=>s+(got[i]===x?1:0),0);
    fraction=hit/Math.max(1,exp.length);ok=hit===exp.length;
  }else if(a.t==="budget"){
    const got=(answer||[]).map(Number),exp=(a.answer||[]).map(Number);
    ok=sameArray(got,exp);
    const diff=exp.reduce((s,x,i)=>s+Math.abs((got[i]??0)-x),0);
    fraction=Math.max(0,1-diff/100);
  }
  return {ok,fraction,why:a.why,right:a.right};
}
function localSubmitLesson(c){
  const results=c.topic.acts.map((a,i)=>localCheckActivity(a,c.ans[i]));
  const score=Math.round(results.reduce((s,r)=>s+r.fraction,0)/Math.max(1,results.length)*100);
  const prev=eduP(c.m,c.t),attempts=eduAttempts(prev)+1,passed=score>=edu.pass;
  const best=Math.max(Number(prev?.score||0),score),completed=passed||prev?.status==="concluida";
  const rec={module_key:c.m,topic_key:c.t,status:completed?"concluida":"em_andamento",score:best,answers_json:JSON.stringify({attempts})};
  edu.prog[eduKey(c.m,c.t)]=rec;saveLocalEduProgress();
  return {score,passed,completed,best,attempts,results};
}

async function loadEducation(){
  if(STATIC_GITHUB_PAGES_MODE){
    setLocalEducation();
    renderTrail();
    return;
  }
  try{
    const r=await api("/api/education");
    edu.local=false;
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
      return `<li><button class="step ${dn2?"done":""} ${lk?"locked":""}" data-open="${m.key}:${t.key}" data-locked="${lk?1:0}"><span class="num" aria-hidden="true">${dn2?"✓":lk?"🔒":k+1}</span><span class="st-t"><b>${esc(t.title)}</b><small>${st}</small></span><span class="st-n" aria-hidden="true">${t.acts.length} atividades</span></button></li>`}).join("")}</ol></article>`}).join("");
}

$("#eduTop").onclick=$("#modules").onclick=e=>{
  const b=e.target.closest("[data-open]");if(!b)return;
  if(b.dataset.locked==="1"&&!confirm("Esta aula é de um passo mais à frente na trilha. Recomendamos concluir a anterior primeiro. Abrir mesmo assim?"))return;
  const [m,t]=b.dataset.open.split(":");openLesson(m,t);
};

function openLesson(m,t){
  const f=edu.flat.find(x=>x.m===m&&x.t===t);if(!f)return;
  edu.cur={...f,step:0,ans:f.topic.acts.map(()=>null),res:f.topic.acts.map(()=>null),result:null,busy:false};
  if(!eduP(m,t)){
    if(edu.local){
      edu.prog[eduKey(m,t)]={status:"em_andamento",module_key:m,topic_key:t,score:0,answers_json:JSON.stringify({attempts:0})};saveLocalEduProgress();
    }else{
      api(`/api/education/${m}/${t}`,{method:"PUT",body:{status:"em_andamento"}}).then(()=>{edu.prog[eduKey(m,t)]={status:"em_andamento",module_key:m,topic_key:t}}).catch(()=>{});
    }
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
    <div class="act-btns">${r?`<button class="btn primary" data-go="${c.step+1}">${c.step<n?"Próxima atividade":"Ver resultado"}</button>`:`<button class="btn primary" id="btnCheck" data-check ${readAns(a)==null?"disabled":""}>Verificar</button>`}</div>`;
  }else{
    body=resultView();
  }
  $("#lessonView").innerHTML=`<div class="card lv">${stepNav()}<div class="stepbody" key="${c.step}">${body}</div></div>`;
  budSum();
  const f=$("#lessonView .stepbody h2,#lessonView legend");f&&(f.tabIndex=-1,f.focus({preventScroll:true}));
  if(c.step===n+1&&c.result?.passed)celebrate();
}

function actInput(a,i){
  const prev=edu.cur.ans[i],dis=edu.cur.res[i];
  if(a.t==="quiz")return `<div class="opts">${a.opts.map((o,k)=>`<label class="opt"><input type="radio" name="q" value="${k}" ${prev===k?"checked":""}><span>${esc(o)}</span></label>`).join("")}</div>`;
  if(a.t==="multi")return `<p class="muted" style="font-size:12px;margin:0 0 8px">Marque todas as corretas.</p><div class="opts">${a.opts.map((o,k)=>`<label class="opt"><input type="checkbox" name="q" value="${k}" ${prev?.includes(k)?"checked":""}><span>${esc(o)}</span></label>`).join("")}</div>`;
  if(a.t==="classify"){const p=prev||[];return `<div class="classify">${a.items.map((it,k)=>`<div class="crow"><span>${esc(it)}</span><div class="seg" role="group" aria-label="${esc(it)}">${a.buckets.map((b,j)=>`<button type="button" class="${p[k]===j?"on":""}" data-cl="${k}:${j}" aria-pressed="${p[k]===j}">${esc(b)}</button>`).join("")}</div></div>`).join("")}</div>`}
  if(a.t==="calc")return `<label class="calc"><span>${esc(a.unit)}</span><input class="input" type="number" inputmode="decimal" step="any" name="q" value="${prev??""}" aria-label="Sua resposta"></label>`;
  if(a.t==="budget"){const p=prev||a.cats.map(()=>0);return `<p class="muted" style="margin:0 0 10px">Renda: <b>${esc(a.total)}</b></p>${a.cats.map((c,k)=>`<div class="bud"><label for="b${k}">${esc(c)}</label><input id="b${k}" type="range" min="0" max="100" step="5" value="${p[k]}" data-bud="${k}"><output id="bo${k}">${p[k]}%</output></div>`).join("")}<p class="bud-sum" id="budSum" aria-live="polite"></p>`}
  return "";
}

function readAns(a){
  const f=$("#actForm");if(!f)return null;
  if(a.t==="quiz"){const x=f.querySelector("input:checked");return x?+x.value:null}
  if(a.t==="multi"){const x=[...f.querySelectorAll("input:checked")].map(i=>+i.value);return x.length?x:null}
  if(a.t==="classify"){const on=[...f.querySelectorAll(".crow")].map(r=>{const b=r.querySelector("button.on");return b?+b.dataset.cl.split(":")[1]:null});return on.every(v=>v!==null)?on:null}
  if(a.t==="calc"){const v=f.querySelector("input").value.trim();return v===""?null:v}
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
      const r=edu.local?localCheckActivity(a,ans):await api(`/api/education/${c.m}/${c.t}/check`,{method:"POST",body:{i,answer:ans}});
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
    const r=edu.local?localSubmitLesson(c):await api(`/api/education/${c.m}/${c.t}/submit`,{method:"POST",body:{answers:c.ans}});
    c.result=r;edu.prog[eduKey(c.m,c.t)]={module_key:c.m,topic_key:c.t,status:r.completed?"concluida":"em_andamento",score:r.best,answers_json:JSON.stringify({attempts:r.attempts})};
    if(edu.local)saveLocalEduProgress();
    renderStep();
  }catch(err){toast(err.message,false);c.step=c.topic.acts.length;renderStep()}
}

async function loadAIStatus(){
  const el=$("#aiStatus");if(!el)return;
  try{
    const s=await api("/api/ai/status");
    el.classList.toggle("ready",!!s.configured);el.classList.toggle("offline",!s.configured);
    el.querySelector("span").textContent=s.configured?`IA conectada${s.model?" • "+s.model:""}`:"Configuração necessária";
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
    $("#classesGrid").innerHTML=r.items.length?r.items.map(c=>`<article class="card classcard"><div><h3>${esc(c.name)}</h3><p class="muted">${esc(c.description||"Sem descrição")}</p></div>${r.role==="professor"?`<div><span class="muted">Código</span><div class="classcode">${c.code_active?esc(c.code):"DESATIVADO"}</div><span class="muted">${c.participants} participante(s)</span></div><div class="goal-actions"><button class="btn small" data-class-edit="${c.id}">Editar</button><button class="btn small" data-renew="${c.id}">Renovar código</button><button class="btn small" data-disable="${c.id}">Desativar código</button><button class="btn small" data-participants="${c.id}">Participantes</button><button class="btn small" data-assign="${c.id}">Atribuir atividade</button><button class="btn small" data-results="${c.id}">Resultados</button><button class="btn small" data-financial-summary="${c.id}">Resumo financeiro</button></div>`:`<div><span class="muted">Professor</span><b style="display:block">${esc(c.teacher_name)}</b></div>`}</article>`).join(""):`<div class="empty"><b>Nenhuma turma ainda</b>${r.role==="aluno"?"Use um código para entrar.":"Crie sua primeira turma."}</div>`;
    const a=await api("/api/assignments");$("#assignmentsList").innerHTML=a.items.length?a.items.map(x=>`<div style="padding:10px 0;border-bottom:1px solid var(--line)"><b>${esc(x.content_key)}</b><div class="muted">${esc(x.class_name)}${x.due_date?" • prazo "+brdate(x.due_date):""}${x.status?" • "+esc(x.status):""}</div></div>`).join(""):`<div class="empty"><b>Nenhuma atividade atribuída</b>Quando houver atribuições, elas aparecerão aqui.</div>`;
  }catch(e){toast(e.message,false)}
}
$("#createClassBtn").onclick=()=>{$("#className").value="";$("#classDescription").value="";$("#classStatus").textContent="";modal("classModal")};
$("#classCreateConfirm").onclick=async()=>{try{const r=await api("/api/classes",{method:"POST",body:{name:$("#className").value,description:$("#classDescription").value||null}});modal("classModal",false);toast("Turma criada. Código: "+r.code);loadClasses()}catch(e){$("#classStatus").textContent=e.message}};
$("#previewClass").onclick=async()=>{try{const r=await api("/api/classes/preview",{method:"POST",body:{code:$("#classCode").value}});const c=r.class;$("#classPreview").innerHTML=`<div class="notice" style="margin-top:10px"><b>${esc(c.name)}</b><br>Professor: ${esc(c.teacher_name)}<br>${esc(c.description||"")}${r.already_member?"<br>Você já participa desta turma.":`<br><button class="btn primary small" id="confirmJoin" style="margin-top:8px">Confirmar entrada</button>`}</div>`;$("#confirmJoin")?.addEventListener("click",async()=>{await api("/api/classes/join",{method:"POST",body:{code:$("#classCode").value}});toast("Entrada na turma confirmada.");$("#classPreview").innerHTML="";loadClasses()})}catch(e){$("#classPreview").innerHTML=`<div class="notice error">${esc(e.message)}</div>`}};

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

$("#classesGrid").onclick=async e=>{const d=e.target.dataset;if(d.financialSummary){await openFinancialSummary(d.financialSummary);return}if(d.classEdit){const current=([...document.querySelectorAll("[data-class-edit]")].find(x=>x.dataset.classEdit===d.classEdit)?.closest(".classcard"));const name=prompt("Novo nome da turma:",current?.querySelector("h3")?.textContent||"");if(name){const description=prompt("Descrição da turma:",current?.querySelector("p")?.textContent||"");await api(`/api/classes/${d.classEdit}`,{method:"PUT",body:{name,description}});toast("Turma atualizada.");loadClasses()}return}if(d.renew){const r=await api(`/api/classes/${d.renew}/code/renew`,{method:"POST"});toast("Novo código: "+r.code);loadClasses()}if(d.disable&&confirm("Desativar este código de entrada?")){await api(`/api/classes/${d.disable}/code/disable`,{method:"POST"});toast("Código desativado.");loadClasses()}if(d.participants){const r=await api(`/api/classes/${d.participants}/participants`);alert(r.items.length?r.items.map(x=>x.name+" — "+x.email).join("\n"):"Nenhum participante ainda.")}if(d.results){const r=await api(`/api/classes/${d.results}/assignment-results`);alert(r.items.length?r.items.map(x=>`${x.student_name} • ${x.content_key} • ${x.status}${x.score!=null?" • "+x.score+"%":""}`).join("\n"):"Ainda não há resultados educativos.")}if(d.assign){const key=prompt("Informe a aula, quiz ou atividade (ex.: poupanca:o-que-e):");if(!key)return;const due=prompt("Prazo opcional em AAAA-MM-DD:","");const instructions=prompt("Instruções adicionais (opcional):","");try{await api(`/api/classes/${d.assign}/assignments`,{method:"POST",body:{content_key:key,content_type:"atividade",due_date:due||null,instructions:instructions||null}});toast("Atividade atribuída.");loadClasses()}catch(err){toast(err.message,false)}}};

function setSwitch(el,on){el.classList.toggle("on",!!on);el.setAttribute("aria-pressed",String(!!on))}
async function loadSettings(){
  state.me=await api("/api/auth/me");paintAvatar($("#profileAvatar"),state.me.avatar,state.me.id);$("#profileName").value=state.me.name;$("#profileEmail").value=state.me.email;
  setSwitch($("#themeSwitch"),state.me.settings.theme==="light");setSwitch($("#tipsSwitch"),!!state.me.settings.tips);setSwitch($("#goalsSwitch"),!!state.me.settings.goal_alerts);setSwitch($("#weeklySwitch"),!!state.me.settings.weekly_email);
  if(state.me.role==="aluno"){const c=await api("/api/classes");$("#privacyClasses").innerHTML=c.items.length?c.items.map(x=>`<div class="switchrow"><div><b>${esc(x.name)}</b><div class="muted">Professor: ${esc(x.teacher_name)} • compartilhar apenas resumos financeiros autorizados</div></div><button class="switch ${x.share_financial?"on":""}" data-share="${x.id}" aria-label="Compartilhar resumo financeiro com a turma ${esc(x.name)}" aria-pressed="${!!x.share_financial}"><i></i></button></div>`).join(""):`<div class="empty">Você ainda não participa de turmas.</div>`}else $("#privacyClasses").innerHTML='<div class="notice">Professores não ativam este acesso pelo próprio perfil. Cada aluno controla o consentimento por turma.</div>';
}
async function saveSettings(patch){try{const r=await api("/api/settings",{method:"PUT",body:patch});state.me.settings=r.settings;document.documentElement.dataset.theme=r.settings.theme;if(state.dashboardData)requestAnimationFrame(()=>renderFinanceChart(state.dashboardData,state.chartType,false));toast("Preferência salva.")}catch(e){toast(e.message,false)}}
$("#themeSwitch").onclick=()=>saveSettings({theme:$("#themeSwitch").classList.contains("on")?"dark":"light"}).then(loadSettings);$("#tipsSwitch").onclick=()=>saveSettings({tips:!$("#tipsSwitch").classList.contains("on")}).then(loadSettings);$("#goalsSwitch").onclick=()=>saveSettings({goal_alerts:!$("#goalsSwitch").classList.contains("on")}).then(loadSettings);$("#weeklySwitch").onclick=()=>saveSettings({weekly_email:!$("#weeklySwitch").classList.contains("on")}).then(loadSettings);
$("#saveProfile").onclick=async()=>{try{const r=await api("/api/profile",{method:"PUT",body:{name:$("#profileName").value}});$("#sideName").textContent=r.name;$("#profileStatus").style.color="var(--green)";$("#profileStatus").textContent=STATIC_GITHUB_PAGES_MODE?"Perfil salvo neste navegador.":"Perfil salvo no banco."}catch(e){$("#profileStatus").style.color="";$("#profileStatus").textContent=e.message}};
$("#privacyClasses").onclick=async e=>{const b=e.target.closest("[data-share]");if(!b)return;const enabled=!b.classList.contains("on");if(enabled&&!confirm("Ativar compartilhamento de resumos financeiros autorizados com o professor desta turma? Comprovantes e conversas privadas ficam de fora."))return;await api(`/api/classes/${b.dataset.share}/share`,{method:"PUT",body:{enabled}});setSwitch(b,enabled);toast(enabled?"Compartilhamento ativado para esta turma.":"Compartilhamento revogado.")};

$("#scanBtn").onclick=()=>{$("#receiptFile").value="";$("#receiptPreview").classList.add("hidden");$("#receiptStatus").className="notice";$("#receiptStatus").textContent="Nada é salvo como transação até você revisar e confirmar. O FinTrack nunca pede senhas bancárias.";state.receiptId=null;modal("scanModal")};
$("#receiptFile").onchange=e=>{const f=e.target.files[0];if(!f)return;$("#receiptPreview").src=URL.createObjectURL(f);$("#receiptPreview").classList.remove("hidden")};
$("#receiptAnalyze").onclick=async()=>{
  const f=$("#receiptFile").files[0],b=$("#receiptAnalyze");if(!f){$("#receiptStatus").className="notice error";$("#receiptStatus").textContent="Selecione uma imagem.";return}
  b.disabled=true;b.textContent="Analisando...";
  try{const fd=new FormData();fd.append("image",f);const up=await api("/api/receipts/upload",{method:"POST",body:fd});state.receiptId=up.id;if(up.duplicate&&!confirm((up.warning||"Este comprovante já foi enviado.")+" Deseja analisar novamente?")){b.disabled=false;b.textContent="Analisar comprovante";return}const r=await api(`/api/receipts/${up.id}/analyze`,{method:"POST"});$("#receiptStatus").className="notice success";$("#receiptStatus").textContent=r.manual?"Imagem carregada. No GitHub Pages, revise e complete os campos manualmente antes de salvar.":"Análise recebida. Revise os campos antes de salvar.";const x=r.result||{};modal("scanModal",false);openTx();if(x.type)$$(`#txTypeTabs button`).forEach(y=>y.classList.toggle("active",y.dataset.value===x.type));fillCategory(x.type||"despesa");if(x.category)$("#txCategory").value=x.category;if(x.amount)$("#txValue").value=String(x.amount).replace(".",",");if(x.description)$("#txDescription").value=x.description;if(x.date)$("#txDate").value=x.date;state.txDirty=true}catch(e){$("#receiptStatus").className="notice error";$("#receiptStatus").textContent=e.message+" O preenchimento manual continua disponível."}finally{b.disabled=false;b.textContent="Analisar comprovante"}
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
