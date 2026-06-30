/**
 * raspar_contatos.js
 * Conecta ao WhatsApp (reutilizando auth do bot), varre todos os grupos
 * e extrai os números de telefone de cada participante.
 *
 * Salva:
 *   - lid_cache.json       : LID → número (reutilizado pelo bot)
 *   - contatos_grupos.json : {numero, nome, grupos[]} (para lookup por nome)
 *
 * Uso:
 *   cd baileys_bot && node raspar_contatos.js
 */

const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
  makeCacheableSignalKeyStore,
} = require('@whiskeysockets/baileys');
const pino   = require('pino');
const qrcode = require('qrcode-terminal');
const fs     = require('fs');
const path   = require('path');

const AUTH_DIR         = path.join(__dirname, 'auth');
const LID_CACHE_FILE   = path.join(__dirname, 'lid_cache.json');
const CONTATOS_FILE    = path.join(__dirname, 'contatos_grupos.json');
const FILA_FILE        = path.join(__dirname, '..', 'mensagens_fila.json');

// ─── Helpers ─────────────────────────────────────────────────────────────────

function carregarJson(file, fallback = {}) {
  try { if (fs.existsSync(file)) return JSON.parse(fs.readFileSync(file, 'utf8')); }
  catch (_) {}
  return fallback;
}

function salvarJson(file, data) {
  fs.writeFileSync(file, JSON.stringify(data, null, 2), 'utf8');
}

function numFromJid(jid = '') {
  if (!jid || jid.endsWith('@lid')) return '';
  const raw = jid.split('@')[0].replace(/\D/g, '');
  return (raw.length >= 10 && raw.length <= 13) ? raw : '';
}

// ─── Main ─────────────────────────────────────────────────────────────────────

async function main() {
  if (!fs.existsSync(AUTH_DIR)) fs.mkdirSync(AUTH_DIR, { recursive: true });

  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
  const { version } = await fetchLatestBaileysVersion();
  console.log(`\n🔌 Conectando ao WhatsApp (Baileys v${version.join('.')})...`);

  const sock = makeWASocket({
    version,
    auth: state,
    logger: pino({ level: 'silent' }),
    browser: ['Contatos Scraper', 'Chrome', '1.0'],
    syncFullHistory: false,
    markOnlineOnConnect: false,
  });

  sock.ev.on('creds.update', saveCreds);

  // Carregar caches existentes
  const lidCache     = carregarJson(LID_CACHE_FILE, {});
  const contatosMap  = {};  // numero → {nome, grupos}

  // Capturar mapeamento LID→phone via contacts.upsert
  sock.ev.on('contacts.upsert', (contacts) => {
    let novos = 0;
    for (const c of contacts) {
      const phoneJid = c.id || '';
      const lidJid   = c.lid || '';
      const nome     = c.name || c.notify || c.verifiedName || '';
      const num      = numFromJid(phoneJid);

      if (num) {
        if (!contatosMap[num]) contatosMap[num] = { nome, grupos: [] };
        if (nome && !contatosMap[num].nome) contatosMap[num].nome = nome;
      }

      if (lidJid && lidJid.endsWith('@lid') && num && !lidCache[lidJid]) {
        lidCache[lidJid] = num;
        novos++;
      }
    }
    if (novos > 0) console.log(`  📱 contacts.upsert: ${novos} novo(s) LID→telefone`);
  });

  // Aguardar conexão (até 3 min para dar tempo de escanear QR)
  await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error('Timeout de conexão (180s)')), 180000);
    sock.ev.on('connection.update', ({ connection, lastDisconnect, qr }) => {
      if (qr) {
        console.log('\n\n📱 ESCANEIE O QR CODE ABAIXO COM O WHATSAPP:\n');
        qrcode.generate(qr, { small: true });
        console.log('\nNo celular: Configurações → Aparelhos Vinculados → Vincular Aparelho\n');
      }
      if (connection === 'open') {
        clearTimeout(timeout);
        console.log('✅ Conectado!\n');
        resolve();
      } else if (connection === 'close') {
        clearTimeout(timeout);
        const code = lastDisconnect?.error?.output?.statusCode;
        reject(new Error(`Conexão encerrada (código ${code})`));
      }
    });
  });

  // Aguardar contacts.upsert por 60 segundos — o WhatsApp envia automaticamente
  // ao conectar e contém o mapeamento LID→telefone de todos os contatos
  console.log('⏳ Aguardando sincronização de contatos (60s)...');
  console.log('   (o WhatsApp envia mapeamentos LID→telefone automaticamente)\n');

  let ultimoLidCount = 0;
  for (let seg = 0; seg < 60; seg += 5) {
    await new Promise(r => setTimeout(r, 5000));
    const atual = Object.keys(lidCache).length;
    if (atual !== ultimoLidCount) {
      console.log(`  📱 ${atual} LIDs mapeados até agora...`);
      ultimoLidCount = atual;
    }
  }

  console.log(`\n📊 Total LIDs mapeados via contacts.upsert: ${Object.keys(lidCache).length}`);

  // Salvar caches
  salvarJson(LID_CACHE_FILE, lidCache);
  salvarJson(CONTATOS_FILE, contatosMap);
  console.log(`✅ lid_cache.json salvo (${Object.keys(lidCache).length} entradas)`);
  console.log(`✅ contatos_grupos.json salvo (${Object.keys(contatosMap).length} contatos)`);

  // Tentar atualizar contatos em mensagens_fila.json onde contato está vazio
  if (fs.existsSync(FILA_FILE)) {
    const fila = carregarJson(FILA_FILE, []);
    let atualizados = 0;

    // Construir mapa nome → numero a partir dos contatos
    const nomeParaNum = {};
    for (const [num, info] of Object.entries(contatosMap)) {
      const nome = (info.nome || '').trim().toLowerCase();
      if (nome && !nomeParaNum[nome]) nomeParaNum[nome] = num;
    }

    for (const msg of fila) {
      if (msg.contato) continue; // já tem contato
      // Tentar por LID se armazenado
      if (msg._lidJid && lidCache[msg._lidJid]) {
        msg.contato = lidCache[msg._lidJid];
        atualizados++;
        continue;
      }
      // Tentar por nome do autor
      const autorLow = (msg.autor || '').trim().toLowerCase();
      if (autorLow && nomeParaNum[autorLow]) {
        msg.contato = nomeParaNum[autorLow];
        atualizados++;
      }
    }

    if (atualizados > 0) {
      salvarJson(FILA_FILE, fila);
      console.log(`📩 ${atualizados} mensagem(ns) na fila atualizada(s) com contato`);
    } else {
      console.log('📩 Nenhuma mensagem na fila precisava de atualização de contato');
    }
  }

  console.log('\n✅ Concluído!\n');
  process.exit(0);
}

main().catch(err => {
  console.error('❌ Erro:', err.message);
  process.exit(1);
});
