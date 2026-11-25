/* FinTrack · Professor: lançar desafios e quizzes, painel de conclusão da turma; aluno: responder quiz.
   Usa os utilitários globais do app.js ($, $$, api, esc, modal, toast, brdate, todayBR, loadClasses). */
let ftTemplates = null, actType = 'desafio';

async function getTemplates() {
  if (!ftTemplates) ftTemplates = await api('/api/teacher/templates');
  return ftTemplates;
}

/* ---------- Lançar atividade ---------- */
function qEditor(q = { q: '', options: ['', '', '', ''], answer: 0, why: '' }, i) {
  const opts = [...q.options]; while (opts.length < 4) opts.push('');
  return `<fieldset class="card act-q" style="padding:12px;margin:0 0 10px">
    <legend class="muted" style="font-size:12px">Pergunta ${i + 1}</legend>
    <div class="field"><textarea class="q-text" maxlength="300" rows="2" aria-label="Enunciado da pergunta ${i + 1}" placeholder="Enunciado">${esc(q.q)}</textarea></div>
    ${opts.slice(0, 5).map((o, j) => `<label style="display:flex;gap:8px;align-items:center;margin-top:6px">
      <input type="radio" name="ans${i}" value="${j}" ${q.answer === j ? 'checked' : ''} aria-label="Marcar alternativa ${j + 1} como correta">
      <input class="q-opt input" maxlength="150" value="${esc(o)}" placeholder="Alternativa ${j + 1}${j > 1 ? ' (opcional)' : ''}" style="flex:1"></label>`).join('')}
    <div class="field" style="margin-top:6px"><input class="q-why" maxlength="300" value="${esc(q.why || '')}" placeholder="Explicação da resposta (opcional, aparece após o aluno concluir)"></div>
    <button type="button" class="btn small danger q-del" style="margin-top:8px">Remover pergunta</button></fieldset>`;
}

function renderQuestions(list) {
  $('#actQuestions').innerHTML = list.map(qEditor).join('');
}

function readQuestions() {
  return $$('#actQuestions .act-q').map((f, i) => {
    const raw = [...f.querySelectorAll('.q-opt')].map(x => x.value.trim());
    const checked = +(f.querySelector(`input[name=ans${i}]:checked`)?.value ?? -1);
    const keep = raw.map((v, j) => ({ v, j })).filter(o => o.v);   // ignora alternativas em branco
    return { q: f.querySelector('.q-text').value.trim(), options: keep.map(o => o.v),
             answer: keep.findIndex(o => o.j === checked), why: f.querySelector('.q-why').value.trim() };
  });
}

function setActType(t) {
  actType = t;
  $$('#actTabs button').forEach(b => { const on = b.dataset.type === t; b.classList.toggle('active', on); b.setAttribute('aria-selected', String(on)); });
  $('#actChallenge').classList.toggle('hidden', t !== 'desafio');
  $('#actQuiz').classList.toggle('hidden', t !== 'quiz');
  const T = ftTemplates;
  const list = t === 'desafio' ? T.challenges : T.quizzes;
  $('#actTemplate').innerHTML = list.map(x => `<option value="${esc(x.key)}">${esc(x.title)}</option>`).join('')
    + `<option value="">${t === 'desafio' ? 'Personalizado' : 'Em branco (escrever minhas perguntas)'}</option>`;
  applyTemplate();
}

function applyTemplate() {
  const key = $('#actTemplate').value, T = ftTemplates;
  if (actType === 'desafio') {
    const c = T.challenges.find(x => x.key === key) || { title: '', kind: 'despesas', target: 1, instructions: '' };
    $('#actTitle').value = c.title; $('#actKind').value = c.kind; $('#actTarget').value = c.target;
    $('#actInstructions').value = c.instructions || '';
  } else {
    const q = T.quizzes.find(x => x.key === key);
    $('#actTitle').value = q ? q.title : ''; $('#actInstructions').value = '';
    renderQuestions(q ? q.questions : [undefined]);
  }
}

async function openActivity(cid) {
  try { await getTemplates(); } catch (e) { toast(e.message, false); return; }
  $('#actClass').value = cid; $('#actDue').value = ''; $('#actDue').min = todayBR(); $('#actStatus').textContent = '';
  $('#actKind').innerHTML = Object.entries(ftTemplates.challenge_kinds).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join('');
  setActType('desafio');
  modal('activityModal');
}

$('#actTabs').onclick = e => { const b = e.target.closest('[data-type]'); if (b) setActType(b.dataset.type); };
$('#actTemplate').onchange = applyTemplate;
$('#actAddQ').onclick = () => {
  const cur = readQuestions(); if (cur.length >= 15) { toast('O quiz pode ter até 15 perguntas.', false); return; }
  const blank = $('#actQuestions'); blank.insertAdjacentHTML('beforeend', qEditor(undefined, cur.length));
  blank.lastElementChild.querySelector('.q-text').focus();
};
$('#actQuestions').onclick = e => {
  if (!e.target.closest('.q-del')) return;
  const cur = readQuestions(); const i = $$('#actQuestions .act-q').indexOf(e.target.closest('.act-q'));
  cur.splice(i, 1); renderQuestions(cur.length ? cur : [undefined]);
};
$('#activityForm').onsubmit = async e => {
  e.preventDefault(); const b = $('#actSubmit'), st = $('#actStatus'); st.textContent = '';
  const body = { type: actType, title: $('#actTitle').value.trim(), due_date: $('#actDue').value || null,
                 instructions: $('#actInstructions').value.trim() || null };
  if (actType === 'desafio') body.config = { kind: $('#actKind').value, target: +$('#actTarget').value };
  else {
    const qs = readQuestions(), bad = qs.findIndex(q => q.q.length < 3 || q.options.length < 2 || q.answer < 0);
    if (bad >= 0) { st.textContent = `Pergunta ${bad + 1}: preencha o enunciado, pelo menos 2 alternativas e marque a correta.`; return; }
    body.config = { questions: qs };
  }
  b.disabled = true;
  try {
    await api(`/api/classes/${$('#actClass').value}/activities`, { method: 'POST', body });
    modal('activityModal', false); toast('Atividade lançada para a turma.'); loadClasses();
  } catch (err) { st.textContent = err.message; } finally { b.disabled = false; }
};

/* ---------- Painel da turma ---------- */
const DASH_COLORS = { concluida: 'var(--green)', pendente: 'var(--yellow)', atrasada: 'var(--red)' };
const TYPE_LABEL = { aula: 'Aula', desafio: 'Desafio', quiz: 'Quiz' };

function stackBar(x) {
  if (!x.total) return '<div class="muted" style="font-size:12px">Sem alunos nesta atividade.</div>';
  const seg = k => x[k] ? `<span style="width:${100 * x[k] / x.total}%;background:${DASH_COLORS[k]}" title="${k}: ${x[k]}"></span>` : '';
  return `<div class="dash-bar" role="img" aria-label="${x.concluida} concluíram, ${x.pendente} pendentes, ${x.atrasada} atrasados, de ${x.total}">${seg('concluida')}${seg('pendente')}${seg('atrasada')}</div>`;
}

async function openDashboard(cid) {
  let r;
  try { r = await api(`/api/classes/${cid}/dashboard`); } catch (e) { toast(e.message, false); return; }
  const o = r.overall;
  const legend = `<div class="dash-legend"><span><i style="background:var(--green)"></i>Concluída</span><span><i style="background:var(--yellow)"></i>Pendente</span><span><i style="background:var(--red)"></i>Atrasada</span></div>`;
  $('#dashBody').innerHTML = !r.activities.length
    ? `<div class="empty"><b>Nenhuma atividade lançada ainda</b>Use “Lançar atividade” ou “Atribuir aula” para começar.</div>`
    : `<div class="dash-top">
        <div class="dash-ring" style="--p:${o.pct}" role="img" aria-label="${o.pct}% das atividades concluídas"><b>${o.pct}%</b><span>concluído</span></div>
        <div><p style="margin:0 0 6px"><b>${o.concluida}</b> de <b>${o.total}</b> entregas concluídas</p>
          <p class="muted" style="margin:0 0 6px">${r.students} aluno(s) · ${r.activities.length} atividade(s)</p>
          ${o.atrasada ? `<p style="margin:0;color:var(--red)"><b>${o.atrasada}</b> entrega(s) atrasada(s)</p>` : ''}${legend}</div></div>
      <h3 style="margin:18px 0 8px">Por atividade</h3>
      ${r.activities.map(a => `<div class="dash-row"><div class="dash-label"><b>${esc(a.title)}</b><span class="muted"> · ${TYPE_LABEL[a.type] || ''}${a.due_date ? ' · prazo ' + brdate(a.due_date) : ''}</span></div>
        ${stackBar(a)}<div class="dash-num">${a.concluida}/${a.total}</div></div>`).join('')}
      <h3 style="margin:18px 0 4px">Por aluno</h3><p class="muted" style="margin:0 0 8px;font-size:12px">Quem concluiu menos aparece primeiro, para você saber quem pode precisar de ajuda.</p>
      ${r.people.length ? r.people.map(p => `<div class="dash-row"><div class="dash-label"><b>${esc(p.name)}</b></div>${stackBar(p)}<div class="dash-num">${p.pct}%</div></div>`).join('')
        : '<div class="muted">Nenhum aluno entrou na turma ainda.</div>'}`;
  modal('dashModal');
}

/* ---------- Aluno: desafios e quizzes ---------- */
function activityExtra(x) {
  if (x.content_type === 'desafio') {
    const t = x.config?.target || 0, p = Math.min(x.progress || 0, t);
    return x.state === 'concluida' ? '' : `<span class="muted" style="font-size:12px">Progresso: ${p} de ${t}</span>`;
  }
  if (x.content_type === 'quiz')
    return `<button class="btn small" data-quiz="${esc(x.id)}">${x.state === 'concluida' ? 'Refazer quiz' : x.attempts ? 'Tentar de novo' : 'Responder quiz'}</button>`;
  return '';
}

let quizCurrent = null;
function openQuiz(id) {
  const x = (window.ftAssignments || []).find(a => a.id === id); if (!x) return;
  quizCurrent = x;
  $('#quizTitle').textContent = x.title; $('#quizStatus').textContent = ''; $('#quizSubmit').classList.remove('hidden');
  $('#quizBody').innerHTML = (x.instructions ? `<p class="muted">${esc(x.instructions)}</p>` : '') +
    (x.config?.questions || []).map((q, i) => `<fieldset class="card" style="padding:12px;margin:0 0 10px" data-qi="${i}">
      <legend><b>${i + 1}. ${esc(q.q)}</b></legend>
      ${q.options.map((o, j) => `<label style="display:flex;gap:8px;align-items:flex-start;margin-top:6px"><input type="radio" name="qa${i}" value="${j}"> <span>${esc(o)}</span></label>`).join('')}
      <div class="q-fb" role="status"></div></fieldset>`).join('');
  modal('quizModal');
}

$('#quizForm').onsubmit = async e => {
  e.preventDefault(); const x = quizCurrent; if (!x) return;
  const n = x.config.questions.length, answers = [];
  for (let i = 0; i < n; i++) {
    const c = document.querySelector(`#quizBody input[name=qa${i}]:checked`);
    if (!c) { $('#quizStatus').textContent = `Responda a pergunta ${i + 1}.`; return; }
    answers.push(+c.value);
  }
  const b = $('#quizSubmit'); b.disabled = true;
  try {
    const r = await api(`/api/assignments/${x.id}/quiz`, { method: 'POST', body: { answers } });
    r.results.forEach((res, i) => {
      const box = document.querySelector(`#quizBody [data-qi="${i}"] .q-fb`);
      const opts = x.config.questions[i].options;
      box.innerHTML = res.ok ? '<span class="badge good">Correta</span>'
        : `<span class="badge bad">Incorreta</span>${res.right != null ? ` <span class="muted">Resposta certa: ${esc(opts[res.right])}</span>` : ''}`;
      if (res.why) box.innerHTML += `<p class="muted" style="margin:6px 0 0">${esc(res.why)}</p>`;
    });
    $('#quizStatus').textContent = r.completed
      ? `Você fez ${r.score}% e concluiu a atividade.${r.passed ? '' : ' (Sua melhor nota continua valendo.)'}`
      : `Você fez ${r.score}%. Para concluir, é preciso ${r.pass}%. Revise as que errou e tente de novo.`;
    if (r.completed) b.classList.add('hidden');
    loadClasses();
  } catch (err) { $('#quizStatus').textContent = err.message; } finally { b.disabled = false; }
};
