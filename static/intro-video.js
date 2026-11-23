/* The backend owns completion. The player resumes only confirmed progress. */
window.FinTrackIntro = (() => {
  let cleanup = () => {};
  async function open(module, topic) {
    const title = {poupanca:'Introdução à poupança',controle:'Introdução ao controle de gastos',planejamento:'Introdução ao planejamento financeiro',investimentos:'Introdução aos investimentos'}[module] || 'Vídeo introdutório';
    cleanup(); edu.cur = null;document.body.classList.add('intro-active');
    $('#modules').classList.add('hidden'); $('#eduTop').classList.add('hidden');
    const root = $('#lessonView'); root.classList.remove('hidden');
    // Acessibilidade: legenda (static/captions/<módulo>.vtt, quando existir) e resumo em texto para quem não ouve.
    const mod = (typeof edu !== 'undefined' && edu.mods || []).find(m => m.key === module);
    const summary = mod ? `<details class="a11y-transcript"><summary>Resumo do vídeo em texto (para quem não pode ouvir)</summary><p>Este vídeo apresenta o módulo <b>${esc(mod.title)}</b> (nível ${mod.level} · ${esc(mod.level_name)}): ${esc(mod.description)}</p><p>Ao terminar, você libera as aulas: ${mod.topics.map(t => esc(t.title)).join(' · ')}.</p></details>` : '';
    root.innerHTML = `<div class="card lv"><button class="btn ghost" id="introBack">← Trilha</button><h2>${esc(title)}</h2><p>Assista até o final para liberar as aulas e atividades deste módulo. Seu progresso é salvo na sua conta.</p><video id="introPlayer" controls playsinline preload="metadata" controlslist="nodownload noplaybackrate" aria-label="${esc(title)}" style="display:block;width:100%;max-height:65vh;background:#000;border-radius:12px"><track kind="captions" srclang="pt-BR" label="Português" src="captions/${encodeURIComponent(module)}.vtt" default></video><p id="introStatus" role="status">Preparando vídeo…</p>${summary}<button class="btn primary" id="introContinue" disabled>Continuar para a aula</button></div>`;
    const video = $('#introPlayer'), label = $('#introStatus'), next = $('#introContinue');
    let active = true, timer, busy = false, saved = 0, completed = false, token;
    // Ao fechar a aba ou sair da página, envia a última posição sem esperar resposta.
    const pagehide = () => { if(token && !completed) fetch(`/api/intro/${module}/tick`,{method:'POST',credentials:'same-origin',keepalive:true,headers:{'Content-Type':'application/json'},body:JSON.stringify({token,position:video.currentTime})}).catch(()=>{}); };
    cleanup = () => { document.body.classList.remove('intro-active');active=false;clearInterval(timer);video.pause();video.removeAttribute('src');video.load();document.removeEventListener('visibilitychange', visibility);window.removeEventListener('pagehide',pagehide); };
    const visibility = () => { if(document.hidden) video.pause(); };
    document.addEventListener('visibilitychange',visibility);window.addEventListener('pagehide',pagehide);
    $('#introBack').onclick = () => { cleanup();loadEducation(); };
    next.onclick = async () => { if(!completed)return;cleanup();await loadEducation();openLesson(module,topic); };
    function display() {
      label.textContent = completed ? 'Vídeo concluído! Você já pode começar a aula.' : `${Math.floor(saved)} de ${Math.ceil(video.duration || 0)} segundos assistidos. Use o play para continuar.`;
      next.disabled = !completed;
    }
    async function tick() {
      if(!active || busy || !token || completed || video.seeking)return;
      busy=true;
      try {
        const r=await api(`/api/intro/${module}/tick`,{method:'POST',body:{token,position:video.currentTime}});
        if(!active)return;
        saved=r.watched;completed=r.completed;
        if(!r.accepted){video.pause();video.currentTime=saved;}
        display();
      } catch(e) { video.pause();label.textContent=e.message+' Seu progresso anterior está salvo. Volte à trilha e reabra o vídeo.'; }
      finally { busy=false;if(active && video.ended && !completed && video.currentTime>saved && video.currentTime-saved<2)setTimeout(tick,350); }
    }
    try {
      const s=await api(`/api/intro/${module}/start`,{method:'POST'});
      if(!active)return;
      token=s.token;saved=s.watched;completed=s.completed;
      video.onloadedmetadata=()=>{if(saved>0)video.currentTime=saved;display();};
      video.onseeked=()=>{if(!completed && video.currentTime>saved+0.5){video.currentTime=saved;label.textContent='Assista ao vídeo na sequência para liberar a aula.';}};
      video.onratechange=()=>{if(video.playbackRate!==1)video.playbackRate=1;};
      video.onpause=()=>{if(active)tick();};
      video.onended=()=>tick();
      video.onerror=()=>{label.textContent='Não foi possível reproduzir o vídeo. Verifique sua conexão e tente de novo; o progresso já salvo continua na sua conta.';if(!$('#introRetry')){label.insertAdjacentHTML('afterend','<button class="btn small" id="introRetry" type="button">Tentar carregar de novo</button>');$('#introRetry').onclick=()=>{$('#introRetry').remove();video.load();};}};
      video.src=`/api/intro/${module}/media`;
      timer=setInterval(()=>{if(!video.paused&&!document.hidden)tick();},1000);
    }catch(e){if(active)label.textContent=e.message;}
  }
  document.addEventListener('fintrack:navigate',()=>cleanup());
  return {open, stop:()=>cleanup()};
})();
