/* FinTrack · Leitura de comprovante no próprio navegador (OCR com Tesseract.js).
   A imagem não sai do aparelho para fazer a leitura; o resultado é só uma SUGESTÃO para a pessoa revisar. */
window.FinTrackOCR = (() => {
  const LIB = 'https://cdn.jsdelivr.net/npm/tesseract.js@5.1.1/dist/tesseract.min.js';
  let loading = null;

  function loadLib() {
    if (window.Tesseract) return Promise.resolve();
    if (!loading) loading = new Promise((ok, fail) => {
      const s = document.createElement('script'); s.src = LIB; s.async = true;
      s.onload = ok; s.onerror = () => { loading = null; fail(new Error('Não foi possível carregar o leitor de comprovantes. Verifique a internet.')); };
      document.head.appendChild(s);
    });
    return loading;
  }

  // Reduz e deixa em tons de cinza: melhora a leitura e acelera no celular.
  async function prepare(file) {
    const img = await createImageBitmap(file);
    const scale = Math.min(1, 1800 / Math.max(img.width, img.height));
    const c = document.createElement('canvas');
    c.width = Math.round(img.width * scale); c.height = Math.round(img.height * scale);
    const g = c.getContext('2d'); g.filter = 'grayscale(1) contrast(1.4)'; g.drawImage(img, 0, 0, c.width, c.height);
    return c;
  }

  const money = s => { const n = parseFloat(s.replace(/\./g, '').replace(',', '.')); return Number.isFinite(n) ? Math.round(n * 100) : null; };
  const MONEY = /(\d{1,3}(?:\.\d{3})*,\d{2})/g;

  function parse(text) {
    const lines = text.split(/\n+/).map(l => l.replace(/\s+/g, ' ').trim()).filter(Boolean);
    const out = { type: 'despesa' };
    // Valor: linha com TOTAL / VALOR A PAGAR / VALOR PAGO; senão, o maior valor do texto.
    const prio = /(total\s*(a\s*pagar|geral|r\$)?|valor\s*(a\s*pagar|pago|total)|vl\.?\s*total)/i;
    let best = null;
    for (const l of lines) if (prio.test(l) && !/(troco|desconto|subtotal|tributos|impostos)/i.test(l)) {
      const v = [...l.matchAll(MONEY)].map(m => money(m[1])).filter(Boolean); if (v.length) { best = Math.max(...v); }
    }
    if (!best) { const all = [...text.matchAll(MONEY)].map(m => money(m[1])).filter(v => v && v < 100000000); if (all.length) best = Math.max(...all); }
    if (best) out.amount_cents = best;
    // Data: dd/mm/aaaa ou dd/mm/aa (não aceita data futura).
    const d = text.match(/\b(\d{2})[\/.-](\d{2})[\/.-](\d{2,4})\b/);
    if (d) {
      let [, dd, mm, yy] = d; if (yy.length === 2) yy = '20' + yy;
      const iso = `${yy}-${mm}-${dd}`, dt = new Date(iso + 'T12:00:00');
      if (!isNaN(dt) && +dd <= 31 && +mm <= 12 && dt <= new Date()) out.date = iso;
    }
    // Descrição: primeira linha "com cara de nome" (letras, sem CNPJ/endereço).
    const name = lines.find(l => /[A-Za-zÀ-ú]{3,}/.test(l) && !/(cnpj|cpf|cupom|fiscal|rua|av\.|avenida|cep|tel|data|hora|extrato|documento|danfe|nfc)/i.test(l) && l.length <= 60);
    if (name) out.description = name.replace(/[^\wÀ-ú .&'-]/g, '').trim().slice(0, 80);
    // Categoria por palavras-chave.
    const t = text.toLowerCase();
    const cats = [
      ['Alimentação', /(mercado|supermerc|padaria|restaurante|lanchonete|ifood|aliment|açougue|hortifruti|pizza|burger|caf[eé])/],
      ['Transporte', /(posto|combust|gasolina|etanol|uber|99|metr[oô]|ônibus|onibus|estacion|ped[áa]gio)/],
      ['Saúde', /(farm[áa]cia|drogaria|droga|hospital|cl[íi]nica|laborat)/],
      ['Educação', /(livraria|papelaria|escola|curso|faculdade)/],
      ['Contas', /(energia|enel|cemig|copel|light|sabesp|[áa]gua|g[áa]s|internet|telefon|claro|vivo|tim\b|oi\b)/],
      ['Lazer', /(cinema|ingresso|teatro|show|bar\b|parque)/],
      ['Assinaturas', /(netflix|spotify|prime|disney|assinatura|youtube)/],
      ['Compras', /(loja|magazine|shopping|roupa|cal[çc]ados|eletr[ôo])/],
    ];
    for (const [cat, re] of cats) if (re.test(t)) { out.category = cat; break; }
    return out;
  }

  async function read(file, onProgress) {
    await loadLib();
    const canvas = await prepare(file);
    const r = await window.Tesseract.recognize(canvas, 'por', {
      logger: m => { if (m.status === 'recognizing text' && onProgress) onProgress(Math.round(m.progress * 100)); },
    });
    const text = r?.data?.text || '';
    if (text.replace(/\s/g, '').length < 8) throw new Error('Não consegui ler texto nessa foto. Tente com mais luz, sem tremer e com o comprovante inteiro na imagem.');
    return { ...parse(text), text };
  }

  return { read, parse };
})();
