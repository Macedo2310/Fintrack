/* FinTrack · Tutorial de boas-vindas (aparece uma vez para contas novas; pode ser revisto em Configurações).
   Usa os utilitários globais do app.js: $, api, toast. */
const TOUR_STEPS = {
  aluno: [
    { img: 'novatx', title: 'Registre seu primeiro gasto', text: 'Clique em “+ Nova transação”, escolha a categoria e o valor. Com o botão Escanear, uma foto do comprovante preenche os dados para você revisar.', alt: 'Janela Nova transação com o botão Adicionar transação em destaque.' },
    { img: 'metas', title: 'Crie uma meta', text: 'Separe dinheiro para um objetivo, como uma reserva de emergência, e acompanhe quanto já guardou e quanto falta.', alt: 'Página Metas com o cartão Reserva de emergência em destaque.' },
    { img: 'educacao', title: 'Aprenda no seu ritmo', text: 'Faça o curso em 4 níveis, com aulas curtas e atividades corrigidas na hora. Seu progresso fica salvo.', alt: 'Página Educação com o botão Começar o curso em destaque.' },
    { img: 'finbot', title: 'Tire dúvidas com o FinBot', text: 'A IA explica conceitos e analisa seus gastos de forma educativa. Ela nunca pede senhas nem movimenta dinheiro.', alt: 'Conversa com o FinBot sobre reserva de emergência.' },
    { img: 'acessibilidade', title: 'Deixe do seu jeito', text: 'No botão azul de acessibilidade, ative perfis para baixa visão, daltonismo, deficiência auditiva, dislexia e mais.', alt: 'Painel de acessibilidade com os perfis prontos em destaque.' },
  ],
  professor: [
    { img: 'painel', title: 'Acompanhe sua turma', text: 'Em Turmas, crie uma turma e compartilhe o código com os alunos. O Painel da turma mostra quem está concluindo as atividades.', alt: 'Painel da turma com gráficos de conclusão por atividade e por aluno.' },
    { img: 'atividade', title: 'Lance atividades', text: 'Use “Lançar atividade” para enviar desafios práticos e quizzes prontos (ou com suas perguntas). O FinTrack corrige sozinho.', alt: 'Janela Lançar atividade com o botão Lançar para a turma em destaque.' },
    { img: 'educacao', title: 'Atribua aulas do curso', text: 'Mande aulas do curso com prazo. Quem atinge a nota mínima aparece como concluído no painel.', alt: 'Página Educação com os níveis do curso.' },
    { img: 'finbot', title: 'Conte com o FinBot', text: 'A IA ajuda a explicar conceitos de finanças de um jeito simples, para você e para os alunos.', alt: 'Conversa com o FinBot.' },
    { img: 'acessibilidade', title: 'Acessível para todos', text: 'No botão azul de acessibilidade, cada pessoa adapta o site para baixa visão, daltonismo, deficiência auditiva e mais.', alt: 'Painel de acessibilidade com os perfis prontos em destaque.' },
  ],
};

function startTour(role, opts = {}) {
  if (document.getElementById('tour')) return;
  const steps = TOUR_STEPS[role === 'professor' ? 'professor' : 'aluno'];
  let i = 0;
  const prevFocus = document.activeElement;
  const el = document.createElement('div');
  el.id = 'tour'; el.className = 'tour';
  el.innerHTML = `<div class="tour-card" role="dialog" aria-modal="true" aria-labelledby="tourTitle" aria-describedby="tourText">
      <figure class="tour-fig"><img id="tourImg" alt="" width="1200" height="675"><span class="tour-tag">Exemplo</span></figure>
      <div class="tour-body">
        <p class="tour-step" id="tourStep"></p>
        <h2 id="tourTitle"></h2>
        <p id="tourText"></p>
        <div class="tour-dots" id="tourDots" aria-hidden="true">${steps.map(() => '<i></i>').join('')}</div>
        <div class="tour-actions">
          <button type="button" class="tour-skip" id="tourSkip">Pular</button>
          <button type="button" class="btn primary tour-next" id="tourNext">Avançar</button>
        </div>
      </div></div>`;
  document.body.appendChild(el);
  document.body.classList.add('tour-open');
  const img = el.querySelector('#tourImg');

  function render() {
    const s = steps[i];
    el.querySelector('.tour-card').classList.remove('in'); void el.offsetWidth; el.querySelector('.tour-card').classList.add('in');
    img.src = `tour/${s.img}.jpg?v=1`; img.alt = s.alt;
    el.querySelector('#tourStep').textContent = `Passo ${i + 1} de ${steps.length}`;
    el.querySelector('#tourTitle').textContent = s.title;
    el.querySelector('#tourText').textContent = s.text;
    [...el.querySelectorAll('#tourDots i')].forEach((d, k) => d.classList.toggle('on', k === i));
    el.querySelector('#tourNext').textContent = i === steps.length - 1 ? 'Começar' : 'Avançar';
    if (steps[i + 1]) new Image().src = `tour/${steps[i + 1].img}.jpg?v=1`;   // pré-carrega o próximo
  }

  async function finish(skipped) {
    document.removeEventListener('keydown', onKey, true);
    el.classList.add('out');
    setTimeout(() => { el.remove(); document.body.classList.remove('tour-open'); prevFocus?.focus?.(); }, 220);
    try { await api('/api/settings', { method: 'PUT', body: { tour_done: true } }); if (typeof state !== 'undefined' && state.me?.settings) state.me.settings.tour_done = true; } catch {}
    if (!skipped && !opts.replay) toast('Tudo pronto! Comece registrando seu primeiro gasto.');
    opts.onClose?.();
  }

  const next = () => { if (i < steps.length - 1) { i++; render(); el.querySelector('#tourNext').focus(); } else finish(false); };
  const prev = () => { if (i > 0) { i--; render(); } };
  el.querySelector('#tourNext').onclick = next;
  el.querySelector('#tourSkip').onclick = () => finish(true);

  function onKey(e) {
    if (e.key === 'Escape') { e.preventDefault(); finish(true); }
    else if (e.key === 'ArrowRight') { e.preventDefault(); next(); }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); prev(); }
    else if (e.key === 'Tab') {                       // mantém o foco dentro do tutorial
      const f = [el.querySelector('#tourSkip'), el.querySelector('#tourNext')];
      const at = f.indexOf(document.activeElement);
      e.preventDefault(); f[(at + (e.shiftKey ? -1 : 1) + f.length) % f.length].focus();
    }
  }
  document.addEventListener('keydown', onKey, true);
  render();
  el.querySelector('#tourNext').focus();
}

document.getElementById('replayTour')?.addEventListener('click', () => startTour(typeof state !== 'undefined' ? state.me?.role : 'aluno', { replay: true }));
