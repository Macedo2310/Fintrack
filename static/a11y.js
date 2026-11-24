/* FinTrack · Painel de acessibilidade. Carregado no <head> de todas as páginas.
   Preferências ficam no próprio aparelho (localStorage) e valem também antes do login.
   Atalho: Alt + A abre o painel. */
(() => {
  const KEY = 'fintrack_a11y';
  const DEFAULTS = { zoom: '100', contrast: false, readableFont: false, spacing: false, links: false, focus: false, cursor: false,
    motion: false, guide: false, cvd: false, filter: 'none', clickToRead: false, rate: '1', libras: false, visualAlerts: false };
  let prefs = { ...DEFAULTS };
  try { prefs = { ...DEFAULTS, ...JSON.parse(localStorage.getItem(KEY) || '{}') }; } catch {}
  const html = document.documentElement;

  function apply() {
    html.classList.remove('a11y-zoom-115', 'a11y-zoom-130', 'a11y-zoom-150', 'a11y-filter-gray', 'a11y-filter-saturate',
      'a11y-filter-protan', 'a11y-filter-deutan', 'a11y-filter-tritan');
    if (prefs.zoom !== '100') html.classList.add('a11y-zoom-' + prefs.zoom);
    if (prefs.filter !== 'none') html.classList.add('a11y-filter-' + prefs.filter);
    const map = { contrast: 'a11y-contrast', readableFont: 'a11y-readable-font', spacing: 'a11y-spacing', links: 'a11y-links',
      focus: 'a11y-focus', cursor: 'a11y-cursor', motion: 'a11y-motion', guide: 'a11y-guide-on', cvd: 'a11y-cvd', visualAlerts: 'a11y-visual-alerts' };
    for (const [k, cls] of Object.entries(map)) html.classList.toggle(cls, !!prefs[k]);
    if (prefs.readableFont && !document.getElementById('a11y-font')) {
      const l = document.createElement('link'); l.id = 'a11y-font'; l.rel = 'stylesheet';
      l.href = 'https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:wght@400;700&display=swap'; document.head.appendChild(l);
    }
    document.dispatchEvent(new CustomEvent('fintrack:a11y', { detail: prefs }));   // gráficos se redesenham com as novas cores
  }
  function save() { try { localStorage.setItem(KEY, JSON.stringify(prefs)); } catch {} apply(); }
  apply();   // antes da página aparecer: evita "piscar" sem as preferências

  // ---------- leitura em voz alta ----------
  const synth = window.speechSynthesis;
  let speakingEl = null;
  function stopSpeaking() { if (synth) synth.cancel(); speakingEl?.classList.remove('a11y-speaking'); speakingEl = null; }
  function speak(text, el) {
    if (!synth) { announce('Este navegador não tem leitura em voz alta.'); return; }
    stopSpeaking();
    text = (text || '').replace(/\s+/g, ' ').trim().slice(0, 6000);
    if (!text) return;
    const u = new SpeechSynthesisUtterance(text);
    u.lang = 'pt-BR'; u.rate = parseFloat(prefs.rate) || 1;
    const voice = synth.getVoices().find(v => v.lang && v.lang.toLowerCase().startsWith('pt-br')) || synth.getVoices().find(v => v.lang && v.lang.toLowerCase().startsWith('pt'));
    if (voice) u.voice = voice;
    if (el) { speakingEl = el; el.classList.add('a11y-speaking'); }
    u.onend = u.onerror = () => { speakingEl?.classList.remove('a11y-speaking'); speakingEl = null; };
    synth.speak(u);
  }
  function readPage() {
    const root = document.querySelector('.modal.open .dialog') || document.querySelector('#lessonView:not(.hidden)') ||
      document.querySelector('.page.active') || document.querySelector('main') || document.body;
    speak(root.innerText, root);
  }
  document.addEventListener('click', e => {
    if (!prefs.clickToRead || e.target.closest('.a11y-panel,.a11y-fab')) return;
    const sel = String(window.getSelection() || '').trim();
    if (sel) { speak(sel); return; }
    const el = e.target.closest('h1,h2,h3,h4,p,li,label,legend,button,a,td,th,summary,.bubble,.notice,.metric,.badge,span,b,small') || e.target;
    speak(el.getAttribute('aria-label') || el.innerText || el.alt || '', el);
  }, true);

  // ---------- Libras (VLibras, serviço oficial do Governo Federal) ----------
  function loadLibras() {
    if (document.getElementById('a11y-vlibras')) return;
    const box = document.createElement('div');
    box.setAttribute('vw', ''); box.className = 'enabled'; box.id = 'a11y-vlibras-box';
    box.innerHTML = '<div vw-access-button class="active"></div><div vw-plugin-wrapper><div class="vw-plugin-top-wrapper"></div></div>';
    document.body.appendChild(box);
    const s = document.createElement('script'); s.id = 'a11y-vlibras'; s.src = 'https://vlibras.gov.br/app/vlibras-plugin.js';
    s.onload = () => { try { new window.VLibras.Widget('https://vlibras.gov.br/app'); window.dispatchEvent(new Event('load')); } catch { announce('Não foi possível iniciar o VLibras.'); } };
    s.onerror = () => announce('O tradutor de Libras (VLibras) não respondeu. Verifique a internet.');
    document.body.appendChild(s);
  }

  // ---------- anúncios para leitor de tela ----------
  let live;
  function announce(msg) { if (!live) return; live.textContent = ''; setTimeout(() => { live.textContent = msg; }, 30); }

  // ---------- filtros de cor (realce para daltonismo) ----------
  const FILTERS = `<svg width="0" height="0" style="position:absolute" aria-hidden="true" focusable="false"><defs>
    <filter id="a11y-protan"><feColorMatrix type="matrix" values="1 0 0 0 0  0.7 1 0 0 0  0.7 0 1 0 0  0 0 0 1 0"/></filter>
    <filter id="a11y-deutan"><feColorMatrix type="matrix" values="1 0.7 0 0 0  0 1 0 0 0  0 0.7 1 0 0  0 0 0 1 0"/></filter>
    <filter id="a11y-tritan"><feColorMatrix type="matrix" values="1 0 0.7 0 0  0 1 0.7 0 0  0 0 1 0 0  0 0 0 1 0"/></filter></defs></svg>`;

  // Perfis de 1 clique: ligam várias opções de uma vez (clicar de novo desliga).
  const PROFILES = [
    { id: 'baixa-visao', icon: '👁️', name: 'Baixa visão', set: { zoom: '130', contrast: true, readableFont: true, links: true, focus: true, cursor: true } },
    { id: 'daltonismo', icon: '🎨', name: 'Daltonismo', set: { cvd: true } },
    { id: 'surdez', icon: '🧏', name: 'Surdez', set: { libras: true, visualAlerts: true } },
    { id: 'dislexia', icon: '📖', name: 'Dislexia / TDAH', set: { readableFont: true, spacing: true, guide: true, motion: true } },
    { id: 'cegueira', icon: '🔊', name: 'Cegueira / voz', set: { clickToRead: true, focus: true, motion: true } },
    { id: 'calma', icon: '🧘', name: 'Menos distração', set: { motion: true, spacing: true } },
  ];
  const profileOn = p => Object.entries(p.set).every(([k, v]) => prefs[k] === v);

  const row = (id, k, icon, text) => `<div class="a11y-row"><span class="a11y-ico" aria-hidden="true">${icon}</span><label for="${id}">${text}</label><input type="checkbox" id="${id}" data-k="${k}"></div>`;
  const TABS = [
    { id: 'perfis', icon: '⭐', name: 'Perfis', html: `<p class="a11y-note">Escolha o que combina com você. Toque de novo para desligar.</p>
      <div class="a11y-profiles">${PROFILES.map(p => `<button type="button" class="a11y-profile" data-profile="${p.id}" aria-pressed="false"><span aria-hidden="true">${p.icon}</span>${p.name}</button>`).join('')}</div>` },
    { id: 'visao', icon: '👁️', name: 'Visão', html: `
      <div class="a11y-row"><span class="a11y-ico" aria-hidden="true">🔠</span><label for="a11y-zoom">Tamanho</label><select id="a11y-zoom" data-k="zoom">
        <option value="100">Normal</option><option value="115">Grande</option><option value="130">Maior</option><option value="150">Muito grande</option></select></div>
      ${row('a11y-contrast', 'contrast', '◐', 'Alto contraste')}${row('a11y-links', 'links', '🔗', 'Destacar botões e links')}
      ${row('a11y-focusx', 'focus', '⬚', 'Foco bem visível')}${row('a11y-cursor', 'cursor', '🖱️', 'Cursor grande')}` },
    { id: 'cores', icon: '🎨', name: 'Cores', html: `
      ${row('a11y-cvd', 'cvd', '🔵', 'Cores para daltonismo')}
      <div class="a11y-row"><span class="a11y-ico" aria-hidden="true">🎛️</span><label for="a11y-filter">Filtro</label><select id="a11y-filter" data-k="filter">
        <option value="none">Nenhum</option><option value="protan">Vermelho fraco</option><option value="deutan">Verde fraco</option>
        <option value="tritan">Azul fraco</option><option value="saturate">Cores vivas</option><option value="gray">Cinza</option></select></div>` },
    { id: 'audicao', icon: '🧏', name: 'Audição', html: `
      ${row('a11y-libras', 'libras', '🤟', 'Tradutor de Libras')}${row('a11y-alerts', 'visualAlerts', '💡', 'Avisos que piscam')}
      <p class="a11y-note">Os vídeos têm resumo em texto embaixo.</p>` },
    { id: 'leitura', icon: '🔊', name: 'Leitura', html: `
      <div class="a11y-btns"><button type="button" class="primary" data-a11y-read>▶ Ler a tela</button><button type="button" data-a11y-stop>■ Parar</button></div>
      ${row('a11y-click', 'clickToRead', '👆', 'Ler o que eu tocar')}
      <div class="a11y-row"><span class="a11y-ico" aria-hidden="true">⏩</span><label for="a11y-rate">Velocidade</label><select id="a11y-rate" data-k="rate">
        <option value="0.8">Devagar</option><option value="1">Normal</option><option value="1.25">Rápida</option><option value="1.5">Muito rápida</option></select></div>
      ${row('a11y-font', 'readableFont', '🅰️', 'Letra fácil de ler')}${row('a11y-spacing', 'spacing', '↔️', 'Mais espaço no texto')}
      ${row('a11y-guide', 'guide', '📏', 'Régua de leitura')}${row('a11y-motion', 'motion', '⏸️', 'Parar animações')}` },
  ];
  const PANEL = `
    <div class="a11y-head"><h2 id="a11y-title">Acessibilidade</h2>
      <button type="button" class="a11y-close" data-a11y-close aria-label="Fechar">✕</button></div>
    <div class="a11y-tabs" role="tablist" aria-label="Categorias">${TABS.map((t, i) => `<button type="button" role="tab" id="a11y-tab-${t.id}" aria-controls="a11y-pane-${t.id}" aria-selected="${i === 0}" tabindex="${i === 0 ? 0 : -1}"><span aria-hidden="true">${t.icon}</span>${t.name}</button>`).join('')}</div>
    ${TABS.map((t, i) => `<div class="a11y-pane" role="tabpanel" id="a11y-pane-${t.id}" aria-labelledby="a11y-tab-${t.id}" ${i === 0 ? '' : 'hidden'}>${t.html}</div>`).join('')}
    <div class="a11y-foot"><button type="button" data-a11y-reset>↺ Restaurar padrão</button><span class="a11y-note">Atalho: Alt + A</span></div>`;

  function build() {
    document.body.insertAdjacentHTML('beforeend', FILTERS);
    live = document.createElement('div'); live.className = 'sr-only'; live.setAttribute('aria-live', 'polite'); document.body.appendChild(live);
    const guide = document.createElement('div'); guide.className = 'a11y-guide'; guide.setAttribute('aria-hidden', 'true'); document.body.appendChild(guide);
    document.addEventListener('mousemove', e => { if (prefs.guide) guide.style.top = (e.clientY - 23) + 'px'; });

    const fab = document.createElement('button');
    fab.type = 'button'; fab.className = 'a11y-fab';
    fab.innerHTML = '<svg aria-hidden="true" viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="4.5" r="1.8" fill="currentColor" stroke="none"/><path d="M5 8.5l7 1.5 7-1.5M12 10v4.5M12 14.5l-3.5 6M12 14.5l3.5 6"/></svg><span class="sr-only">Acessibilidade</span>';
    fab.title = 'Acessibilidade';
    fab.setAttribute('aria-expanded', 'false'); fab.setAttribute('aria-controls', 'a11y-panel');
    const panel = document.createElement('div');
    panel.id = 'a11y-panel'; panel.className = 'a11y-panel'; panel.setAttribute('role', 'dialog'); panel.setAttribute('aria-labelledby', 'a11y-title');
    panel.innerHTML = PANEL;
    document.body.append(fab, panel);

    const inputs = [...panel.querySelectorAll('[data-k]')];
    const syncUI = () => {
      inputs.forEach(el => { if (el.type === 'checkbox') el.checked = !!prefs[el.dataset.k]; else el.value = prefs[el.dataset.k]; });
      panel.querySelectorAll('[data-profile]').forEach(b => b.setAttribute('aria-pressed', String(profileOn(PROFILES.find(p => p.id === b.dataset.profile)))));
    };
    const changed = (k, before) => {
      if (k === 'libras' || k === undefined) { if (prefs.libras && !before.libras) loadLibras(); if (!prefs.libras && before.libras) announce('O tradutor de Libras sai ao recarregar a página.'); }
      if (!prefs.clickToRead) stopSpeaking();
    };
    inputs.forEach(el => el.addEventListener('change', () => {
      const before = { ...prefs }; const k = el.dataset.k;
      prefs[k] = el.type === 'checkbox' ? el.checked : el.value;
      save(); syncUI(); changed(k, before); announce('Preferência atualizada.');
    }));
    panel.querySelectorAll('[data-profile]').forEach(b => b.addEventListener('click', () => {
      const p = PROFILES.find(x => x.id === b.dataset.profile), before = { ...prefs }, on = profileOn(p);
      for (const [k, v] of Object.entries(p.set)) prefs[k] = on ? DEFAULTS[k] : v;
      save(); syncUI(); changed(undefined, before);
      announce(`Perfil ${p.name} ${on ? 'desligado' : 'ligado'}.`);
      if (!on && p.id === 'cegueira') speak('Leitura em voz alta ligada. Toque em qualquer texto para ouvir.');
    }));
    // Abas: setas esquerda/direita trocam de aba (padrão ARIA).
    const tabs = [...panel.querySelectorAll('[role=tab]')];
    const selectTab = (tab, focus) => {
      tabs.forEach(t => { const on = t === tab; t.setAttribute('aria-selected', String(on)); t.tabIndex = on ? 0 : -1;
        panel.querySelector('#' + t.getAttribute('aria-controls')).hidden = !on; });
      if (focus) tab.focus();
    };
    tabs.forEach((t, i) => {
      t.addEventListener('click', () => selectTab(t));
      t.addEventListener('keydown', e => {
        if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') { e.preventDefault(); selectTab(tabs[(i + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length], true); }
      });
    });
    syncUI();

    const open = show => { panel.classList.toggle('open', show); fab.setAttribute('aria-expanded', String(show)); if (show) panel.querySelector('[role=tab][aria-selected=true]')?.focus(); else fab.focus(); };
    fab.addEventListener('click', () => open(!panel.classList.contains('open')));
    panel.querySelector('[data-a11y-close]').addEventListener('click', () => open(false));
    panel.querySelector('[data-a11y-read]').addEventListener('click', readPage);
    panel.querySelector('[data-a11y-stop]').addEventListener('click', stopSpeaking);
    panel.querySelector('[data-a11y-reset]').addEventListener('click', () => {
      prefs = { ...DEFAULTS }; save(); stopSpeaking(); syncUI();
      announce('Preferências de acessibilidade restauradas.');
    });
    panel.addEventListener('keydown', e => { if (e.key === 'Escape') { e.stopPropagation(); open(false); } });
    document.addEventListener('keydown', e => { if (e.altKey && (e.key === 'a' || e.key === 'A')) { e.preventDefault(); open(!panel.classList.contains('open')); } });
    if (prefs.libras) loadLibras();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', build); else build();

  window.FinTrackA11y = { speak, stop: stopSpeaking, prefs: () => ({ ...prefs }) };
})();
