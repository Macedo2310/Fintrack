/* Financial data and persistent, account-scoped in-app reminders. */
(() => {
  const nav = document.querySelector('.nav');
  const navButton = document.createElement('button');
  navButton.dataset.page = 'notifications';
  navButton.textContent = 'Lembretes';
  navButton.onclick = () => setPage('notifications');
  nav.insertBefore(navButton, nav.lastElementChild);
  const bell = document.createElement('button');
  bell.className = 'btn'; bell.id = 'reminderBell'; bell.textContent = 'Lembretes';
  bell.onclick = () => setPage('notifications');
  document.querySelector('.top-actions').prepend(bell);

  const market = document.createElement('div');
  market.className = 'card market-panel';
  market.innerHTML = `<h2>Moedas e indicadores</h2><p class="muted">Referências educativas do Banco Central do Brasil, consultadas pelo servidor. Dólar e euro: último boletim PTAX do dia (o fechamento sai por volta das 13h); pode diferir da cotação comercial de bancos e casas de câmbio e não é preço negociável; não representa saldo ou investimento seu.</p><div id="marketItems" class="market-grid" aria-live="polite">Carregando indicadores…</div><button class="btn small" id="marketRetry">Atualizar indicadores</button>`;
  document.querySelector('#page-dashboard .metrics').after(market);
  const page = document.createElement('section');
  page.id = 'page-notifications'; page.className = 'page';
  page.innerHTML = `<div class="pagehead"><div><h1>Seus lembretes</h1><p>Metas, aprendizado e atenção ao seu orçamento.</p></div><button class="btn" id="readAll">Marcar todos como lidos</button></div>
    <div class="card"><h2>O que você quer acompanhar?</h2><p class="muted">Lembretes aparecem somente dentro do FinTrack, quando você abre ou usa o app. Não são notificações push, não chegam com o navegador fechado e não são enviados por e-mail. Avisos antigos permanecem no histórico, e marcar como lido não recria o mesmo aviso.</p>
    <form id="reminderForm"><div class="reminder-options"><label><input type="checkbox" id="reminderGoals"> Prazos e conclusão de metas</label><label><input type="checkbox" id="reminderLessons"> Aulas e atividades pendentes</label><label><input type="checkbox" id="reminderSpending"> Atenção aos gastos</label></div>
    <div class="field"><label for="monthlyBudget">Limite mensal de gastos (R$)</label><input id="monthlyBudget" type="text" inputmode="decimal" placeholder="Ex.: 1.500,00" maxlength="18"><small class="muted">Avisos em 80% e 100% do limite. Deixe vazio para comparar despesas e receitas do mês.</small></div><button class="btn primary" type="submit">Salvar preferências</button><p id="reminderStatus" role="status"></p></form></div>
    <div id="reminderItems" aria-live="polite"></div><div class="reminder-pagination"><button class="btn" id="reminderPrev">Anterior</button><span id="reminderPage"></span><button class="btn" id="reminderNext">Próxima</button></div>`;
  document.querySelector('#workspace').append(page);
  let currentPage = 1, loading = false;
  async function loadMarket() {
    const button = $('#marketRetry'); button.disabled = true;
    try {
      const data = await api('/api/market');
      const names = {USD:'Dólar', EUR:'Euro', SELIC:'Meta Selic', IPCA:'IPCA'};
      const value = item => item.key === 'USD' || item.key === 'EUR'
        ? Number(item.value).toLocaleString('pt-BR', {style:'currency', currency:'BRL', minimumFractionDigits:2, maximumFractionDigits:2})
        : Number(item.value).toLocaleString('pt-BR', {minimumFractionDigits:2, maximumFractionDigits:2});
      $('#marketItems').innerHTML = data.items.map(item => `<article><span>${esc(item.label)}</span><strong>${esc(value(item))}</strong><small>${esc(item.unit)}</small><small>${esc(item.reference || 'Referência: ' + brdate(item.observed_at))}</small><small>Consulta: ${esc(new Date(item.fetched_at).toLocaleString('pt-BR'))}</small>${item.stale ? '<span class="market-status old">Antigo: último valor salvo</span>' : '<span class="market-status ok">Atualizado</span>'}<small>Fonte: ${esc(item.source || 'Banco Central do Brasil')}</small></article>`).join('')
        + data.unavailable.map(k => `<article><span>${esc(names[k] || k)}</span><strong>—</strong><span class="market-status off">Indisponível</span><small>A fonte oficial não respondeu e não há valor salvo. Nenhum número é estimado.</small></article>`).join('');
    } catch (e) { $('#marketItems').textContent = e.message; }
    finally { button.disabled = false; }
  }
  async function loadReminders() {
    if (loading || !state.me) return;
    loading = true;
    try {
      const data = await api('/api/notifications?page=' + currentPage);
      bell.textContent = data.unread ? `Lembretes (${data.unread})` : 'Lembretes';
      bell.setAttribute('aria-label', `${data.unread} lembretes não lidos`);
      $('#reminderItems').innerHTML = data.items.length ? data.items.map(n => `<article class="card reminder-item ${n.read_at ? 'is-read' : ''}"><div><small>${esc(new Date(n.created_at).toLocaleString('pt-BR'))} · ${n.read_at ? 'Lido' : 'Não lido'}</small><h2>${esc(n.title)}</h2><p>${esc(n.body)}</p></div><button class="btn" data-notification="${esc(n.id)}" data-destination="${esc(n.destination)}">${n.read_at ? 'Abrir' : 'Marcar como lido e abrir'} ${({goals:'metas', education:'aulas', classes:'turmas', transactions:'lançamentos'})[n.destination] || ''}</button></article>`).join('') : '<div class="empty">Tudo em dia. Seus próximos lembretes aparecerão aqui.</div>';
      $('#reminderPrev').disabled = currentPage <= 1;
      $('#reminderNext').disabled = currentPage * 30 >= data.total;
      $('#reminderPage').textContent = `Página ${currentPage}`;
      $('#reminderItems').querySelectorAll('button').forEach(button => button.onclick = async () => {
        button.disabled = true;
        try { await api(`/api/notifications/${button.dataset.notification}/read`, {method:'POST'}); setPage(button.dataset.destination); await loadReminders(); }
        catch (e) { toast(e.message, false); } finally { button.disabled = false; }
      });
    } catch (e) { $('#reminderItems').textContent = e.message; }
    finally { loading = false; }
  }
  async function loadPreferences() {
    try {
      const [prefs, me] = await Promise.all([api('/api/notifications/preferences'),api('/api/auth/me')]);
      $('#reminderGoals').checked = Boolean(me.settings.goal_alerts);
      $('#reminderLessons').checked = Boolean(prefs.lessons);
      $('#reminderSpending').checked = Boolean(prefs.spending);
      $('#monthlyBudget').value = prefs.monthly_budget_cents ? (prefs.monthly_budget_cents / 100).toFixed(2).replace('.', ',') : '';
    } catch (e) { $('#reminderStatus').textContent = e.message; }
  }
  $('#reminderForm').onsubmit = async event => {
    event.preventDefault();
    const raw = $('#monthlyBudget').value.trim();
    if (raw && !/^(?:\d+|\d{1,3}(?:\.\d{3})+)(?:,\d{1,2})?$/.test(raw)) { $('#reminderStatus').textContent = 'Use um valor como 1500 ou 1.500,00.'; return; }
    const amount = raw ? Math.round(Number(raw.replace(/\./g,'').replace(',','.')) * 100) : 0;
    if (!Number.isSafeInteger(amount) || amount > 100000000000) { $('#reminderStatus').textContent = 'O limite informado é muito alto.'; return; }
    const button = event.submitter; button.disabled = true;
    try {
      await api('/api/notifications/preferences', {method:'PUT',body:{lessons:$('#reminderLessons').checked,spending:$('#reminderSpending').checked,monthly_budget_cents:amount}});
      const result = await api('/api/settings', {method:'PUT',body:{goal_alerts:$('#reminderGoals').checked}});
      state.me.settings = {...state.me.settings,...result.settings};
      $('#reminderStatus').textContent = 'Preferências salvas.';
      await loadReminders();
    } catch (e) { $('#reminderStatus').textContent = e.message; }
    finally { button.disabled = false; }
  };
  $('#readAll').onclick = async () => { try { await api('/api/notifications/read-all', {method:'POST'}); await loadReminders(); } catch(e) { toast(e.message,false); } };
  $('#reminderPrev').onclick = () => { currentPage--; loadReminders(); };
  $('#reminderNext').onclick = () => { currentPage++; loadReminders(); };
  $('#marketRetry').onclick = loadMarket;
  // Indicadores: recarrega ao voltar ao painel ou à aba e a cada 5 min com o painel visível.
  let marketAt = 0;
  const refreshMarket = (force = false) => {
    if (document.hidden || !$('#page-dashboard')?.classList.contains('active')) return;
    if (force || Date.now() - marketAt > 60000) { marketAt = Date.now(); loadMarket(); }
  };
  document.addEventListener('fintrack:navigate', event => {
    if (event.detail === 'notifications') { loadPreferences(); loadReminders(); }
    if (event.detail === 'dashboard') setTimeout(refreshMarket, 0);
  });
  setInterval(() => refreshMarket(true), 5 * 60000);
  document.addEventListener('visibilitychange', () => refreshMarket());
  // Boot is asynchronous in app.js; wait for its first successful navigation.
  document.addEventListener('fintrack:navigate', () => { marketAt = Date.now(); loadMarket(); loadReminders(); }, {once:true});
  setInterval(() => { if (!document.hidden) loadReminders(); }, 60000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) loadReminders(); });
})();
