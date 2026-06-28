// ============================================================
//  ENVIO EM MASSA WHATSAPP - Nicolas Sodoski
//  Como usar:
//  1. Abra o WhatsApp Web no Chrome (web.whatsapp.com)
//  2. Pressione F12 para abrir o Console
//  3. Cole TODO este script e pressione Enter
//  4. Chame: iniciar(contatos, msg1, msg2)
// ============================================================

// ---- CONFIGURAÇÃO ----
const ESPERA_BOTAO_MS = 12000;  // tempo máximo esperando botão aparecer (ms)
const DELAY_ENTRE_ENVIOS = 3000; // pausa entre pessoas (ms)

// ---- ESTADO ----
const CHAVE_FILA  = '_em_fila';
const CHAVE_IDX   = '_em_idx';
const CHAVE_LOG   = '_em_log';
let _pausado = false;

// ---- FUNÇÕES PRINCIPAIS ----

async function iniciar(contatos, msg1, msg2) {
  // contatos: array de objetos { num: '554499...', nome: 'João' }
  // msg1: primeira mensagem (ex: 'Opa! Tudo joia?')
  // msg2: segunda mensagem

  // Filtrar já enviados e sem número
  const log = JSON.parse(localStorage.getItem(CHAVE_LOG) || '[]');
  const jaEnviados = new Set(log.filter(l => l.status === 'enviado').map(l => l.num));
  const fila = contatos.filter(c => c.num && c.num.length >= 12 && !jaEnviados.has(c.num));

  // Carregar estado anterior se existir
  const filaAtual = JSON.parse(localStorage.getItem(CHAVE_FILA) || 'null');
  if (!filaAtual) {
    localStorage.setItem(CHAVE_FILA, JSON.stringify(fila));
    localStorage.setItem(CHAVE_IDX, '0');
  }

  console.log(`✅ Fila pronta: ${fila.length} contatos. Enviados antes: ${jaEnviados.size}`);
  console.log('▶️  Iniciando... Use pausar() para parar.');
  _pausado = false;
  await _loop(msg1, msg2);
}

async function retomar(msg1, msg2) {
  _pausado = false;
  console.log('▶️  Retomando...');
  await _loop(msg1, msg2);
}

function pausar() {
  _pausado = true;
  console.log('⏸️  Pausado. Use retomar(msg1, msg2) para continuar.');
}

function status() {
  const log = JSON.parse(localStorage.getItem(CHAVE_LOG) || '[]');
  const fila = JSON.parse(localStorage.getItem(CHAVE_FILA) || '[]');
  const idx = parseInt(localStorage.getItem(CHAVE_IDX) || '0');
  const enviados = log.filter(l => l.status === 'enviado').length;
  const invalidos = log.filter(l => l.status === 'invalido').length;
  console.log(`📊 Status:`);
  console.log(`   ✅ Enviados: ${enviados}`);
  console.log(`   ❌ Inválidos: ${invalidos}`);
  console.log(`   ⏳ Restam: ${fila.length - idx}`);
  return { enviados, invalidos, restam: fila.length - idx };
}

function resetar() {
  localStorage.removeItem(CHAVE_FILA);
  localStorage.removeItem(CHAVE_IDX);
  localStorage.removeItem(CHAVE_LOG);
  console.log('🔄 Estado resetado. Pronto para nova campanha.');
}

function exportarLog() {
  const log = JSON.parse(localStorage.getItem(CHAVE_LOG) || '[]');
  const csv = 'numero,nome,status,data\n' + log.map(l =>
    `${l.num},"${l.nome}",${l.status},${new Date(l.ts).toLocaleString('pt-BR')}`
  ).join('\n');
  const blob = new Blob([csv], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = 'resultado_envio.csv'; a.click();
  console.log('📁 Log exportado!');
}

// ---- LOOP INTERNO ----

async function _loop(msg1, msg2) {
  const fila = JSON.parse(localStorage.getItem(CHAVE_FILA) || '[]');
  let idx = parseInt(localStorage.getItem(CHAVE_IDX) || '0');

  while (idx < fila.length && !_pausado) {
    const contato = fila[idx];
    console.log(`📤 [${idx+1}/${fila.length}] Enviando para ${contato.nome || contato.num}...`);

    const resultado = await _enviarPara(contato.num, msg1, msg2);

    const log = JSON.parse(localStorage.getItem(CHAVE_LOG) || '[]');
    log.push({ num: contato.num, nome: contato.nome || '', status: resultado, ts: Date.now() });
    localStorage.setItem(CHAVE_LOG, JSON.stringify(log));

    idx++;
    localStorage.setItem(CHAVE_IDX, String(idx));

    const emoji = resultado === 'enviado' ? '✅' : resultado === 'invalido' ? '❌' : '⚠️';
    console.log(`   ${emoji} ${resultado} — ${contato.nome || contato.num}`);

    if (idx < fila.length && !_pausado) {
      await _esperar(DELAY_ENTRE_ENVIOS);
    }
  }

  if (!_pausado) {
    const log = JSON.parse(localStorage.getItem(CHAVE_LOG) || '[]');
    console.log(`\n🎉 Concluído! ${log.filter(l=>l.status==='enviado').length} mensagens enviadas.`);
    console.log('   Use exportarLog() para baixar o resultado em CSV.');
  }
}

async function _enviarPara(num, msg1, msg2) {
  // Navegar para o chat
  window.location.href = `https://web.whatsapp.com/send?phone=${num}&text=${encodeURIComponent(msg1)}`;

  // Aguardar botão de envio ou popup de número inválido
  const inicio = Date.now();
  let btn = null, popup = null;
  while (Date.now() - inicio < ESPERA_BOTAO_MS) {
    await _esperar(500);
    btn = document.querySelector('[aria-label="Enviar"]') || document.querySelector('[data-testid="send"]');
    popup = document.querySelector('[data-testid="popup-contents"]');
    if (btn || popup) break;
  }

  if (popup) {
    document.querySelector('[data-testid="popup-confirm-button"]')?.click();
    await _esperar(500);
    return 'invalido';
  }

  if (!btn) return 'sem_botao';

  // Garantir msg1 na caixa e enviar
  const box = document.querySelector('[data-testid="conversation-compose-box-input"]');
  if (box) {
    box.focus();
    document.execCommand('selectAll', false, null);
    document.execCommand('insertText', false, msg1);
    await _esperar(400);
  }
  btn.click();
  await _esperar(1800);

  // Enviar msg2
  const box2 = document.querySelector('[data-testid="conversation-compose-box-input"]');
  if (box2 && msg2) {
    box2.focus();
    document.execCommand('insertText', false, msg2);
    await _esperar(800);
    const btn2 = document.querySelector('[aria-label="Enviar"]') || document.querySelector('[data-testid="send"]');
    btn2?.click();
    await _esperar(800);
  }

  return 'enviado';
}

function _esperar(ms) {
  return new Promise(r => setTimeout(r, ms));
}

// ---- EXEMPLO DE USO ----
console.log(`
✅ Script de envio em massa carregado!

📋 COMO USAR:

1) Prepare seus contatos:
   const contatos = [
     { num: '554499123456', nome: 'João' },
     { num: '554488654321', nome: 'Maria' },
     // ... cole sua lista aqui
   ];

2) Inicie o envio:
   iniciar(contatos,
     'Opa! Tudo joia?',
     'Você que tá a mais tempo no mercado aqui em maringá, tem mais grupos de corretores como esse aqui?'
   );

3) Para pausar:    pausar()
   Para retomar:   retomar(msg1, msg2)
   Ver progresso:  status()
   Baixar log:     exportarLog()
   Reiniciar tudo: resetar()
`);
