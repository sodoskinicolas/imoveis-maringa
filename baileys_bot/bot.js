/**
 * bot.js — Leitor de Grupos WhatsApp com Baileys
 *
 * Conecta diretamente ao WhatsApp via WebSocket (sem browser).
 * Monitora grupos de corretores e salva mensagens de imóveis na fila.
 *
 * Primeira execução: escanear QR Code no terminal.
 * Reinicializações seguintes: reconecta automaticamente.
 */

const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
  isJidGroup,
  downloadMediaMessage,
} = require('@whiskeysockets/baileys');
const pino    = require('pino');
const qrcode  = require('qrcode-terminal');
const fs      = require('fs');
const path    = require('path');

// ─── Caminhos ────────────────────────────────────────────────────────────────
const BASE_DIR      = path.join(__dirname, '..');
const AUTH_DIR      = path.join(__dirname, 'auth');
const FILA_FILE     = path.join(BASE_DIR,  'mensagens_fila.json');
const CONFIG_FILE   = path.join(__dirname, 'config.json');
const LOG_FILE      = path.join(__dirname, 'baileys.log');
const IMG_DIR       = path.join(__dirname, 'imagens');
const LOCK_FILE     = path.join(__dirname, 'bot.lock');
const LID_CACHE_FILE= path.join(__dirname, 'lid_cache.json');

// ─── Lock: garante apenas uma instância ──────────────────────────────────────
if (fs.existsSync(LOCK_FILE)) {
  const existingPid = parseInt(fs.readFileSync(LOCK_FILE, 'utf8').trim(), 10);
  try {
    process.kill(existingPid, 0); // lança exceção se o processo não existe
    console.error(`[bot] Já existe uma instância rodando (PID ${existingPid}). Saindo.`);
    process.exit(0);
  } catch (e) {
    // Processo não existe — lock file obsoleto, remover
    fs.unlinkSync(LOCK_FILE);
  }
}
fs.writeFileSync(LOCK_FILE, String(process.pid));
// Remover lock ao sair (qualquer motivo)
const _removerLock = () => { try { fs.unlinkSync(LOCK_FILE); } catch (_) {} };
process.on('exit',    _removerLock);
process.on('SIGINT',  () => { _removerLock(); process.exit(0); });
process.on('SIGTERM', () => { _removerLock(); process.exit(0); });

// Criar pasta de imagens se não existir
if (!fs.existsSync(IMG_DIR)) fs.mkdirSync(IMG_DIR, { recursive: true });

// ─── Logger ──────────────────────────────────────────────────────────────────
const logStream = fs.createWriteStream(LOG_FILE, { flags: 'a' });
function log(msg) {
  const ts = new Date().toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo' });
  const line = `[${ts}] ${msg}`;
  process.stdout.write(line + '\n'); // só stdout (nohup redireciona para baileys.log)
  // logStream separado só se quiser log independente do nohup
}

// ─── Config ──────────────────────────────────────────────────────────────────
function getConfig() {
  if (fs.existsSync(CONFIG_FILE)) {
    try { return JSON.parse(fs.readFileSync(CONFIG_FILE, 'utf8')); } catch (e) {}
  }
  return { grupos: [] }; // lista vazia = monitorar TODOS os grupos
}

// ─── Cache de metadados dos grupos ───────────────────────────────────────────
const grupoCache = {};    // jid → nomeGrupo

// Cache LID → número real, persistido em arquivo para sobreviver restarts
function _carregarLidCache() {
  try {
    if (fs.existsSync(LID_CACHE_FILE))
      return JSON.parse(fs.readFileSync(LID_CACHE_FILE, 'utf8'));
  } catch (_) {}
  return {};
}
function _salvarLidCache(cache) {
  try { fs.writeFileSync(LID_CACHE_FILE, JSON.stringify(cache, null, 2)); } catch (_) {}
}
const lidPhoneCache = _carregarLidCache(); // lid@lid → número de telefone real

/**
 * Resolve um LID para telefone real usando metadados do grupo.
 * O WhatsApp envia participants com { id: '123@lid', phoneJid: '5544...@s.whatsapp.net' }
 * em grupos. Armazena em cache para não repetir chamadas.
 */
async function resolverLid(sock, grupoJid, lidJid) {
  if (lidPhoneCache[lidJid]) return lidPhoneCache[lidJid];
  try {
    const meta = await sock.groupMetadata(grupoJid);
    for (const p of meta.participants) {
      if (p.id === lidJid) {
        // phoneJid é o campo com o número real: '5544999...@s.whatsapp.net'
        const phoneJid = p.phoneJid || p.phone_jid || p.pn || '';
        if (phoneJid) {
          const num = phoneJid.split('@')[0].replace(/\D/g, '');
          if (num.length >= 10 && num.length <= 13) {
            lidPhoneCache[lidJid] = num;
            _salvarLidCache(lidPhoneCache);
            log(`📱 LID resolvido via groupMetadata: ${lidJid} → ${num}`);
            return num;
          }
        }
        // Tentar ID numérico do próprio LID como fallback secundário
        const rawId = p.id.split('@')[0].replace(/\D/g, '');
        if (rawId.length >= 10 && rawId.length <= 13) {
          lidPhoneCache[lidJid] = rawId;
          _salvarLidCache(lidPhoneCache);
          return rawId;
        }
      }
    }
  } catch (_) {}
  // Última tentativa: API interna do Baileys
  try {
    const phone = await sock.getPhoneNumber(lidJid);
    if (phone) {
      const num = phone.replace(/\D/g, '');
      if (num.length >= 10 && num.length <= 13) {
        lidPhoneCache[lidJid] = num;
        _salvarLidCache(lidPhoneCache);
        log(`📱 LID resolvido via getPhoneNumber: ${lidJid} → ${num}`);
        return num;
      }
    }
  } catch (_) {}
  return '';
}

// ─── Fila de mensagens ───────────────────────────────────────────────────────
function salvarNaFila(entrada) {
  let fila = [];
  if (fs.existsSync(FILA_FILE)) {
    try { fila = JSON.parse(fs.readFileSync(FILA_FILE, 'utf8')); } catch (e) { fila = []; }
  }
  // Deduplicar por msgId — Baileys pode disparar o mesmo evento duas vezes
  if (entrada.msgId && fila.some(m => m.msgId === entrada.msgId)) {
    return; // já está na fila
  }
  fila.push(entrada);
  fs.writeFileSync(FILA_FILE, JSON.stringify(fila, null, 2), 'utf8');
}

// ─── Grupos a IGNORAR (moradores, família, etc.) ─────────────────────────────
const GRUPOS_BLOQUEADOS = /moradores|família|family|condomínio residencial|síndico|assembleia/i;

// ─── Filtro básico: pode ser anúncio de imóvel? ──────────────────────────────
const PALAVRAS_IMOVEL = /vend[ao]|alug[ao]|apartamento|apto|casa\b|terreno|sala comercial|loja|m[²2]\b|quarto|dormit|suíte|suite|vaga|garagem|\br\$|condomín|bairro|imóvel|imovel|\d+\s*m\s*[²2]|cliente\s+(?:procura|busca|quer|precisa|aprovad)|procuro\b|busco\b|preciso\s+de\s+(?:apto|apartamento|casa)|financiamento\s+aprovado/i;

function podeSerImovel(texto, temImagem) {
  if (temImagem) return true;
  return PALAVRAS_IMOVEL.test(texto);
}

// ─── Bot principal ───────────────────────────────────────────────────────────
async function iniciarBot() {
  if (!fs.existsSync(AUTH_DIR)) fs.mkdirSync(AUTH_DIR, { recursive: true });

  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
  const { version } = await fetchLatestBaileysVersion();

  log(`Iniciando bot com Baileys v${version.join('.')}`);

  const sock = makeWASocket({
    version,
    auth: state,
    logger: pino({ level: 'silent' }), // silencia logs internos do Baileys
    browser: ['Imoveis Maringá Bot', 'Chrome', '1.0'],
    syncFullHistory: false,          // não baixar histórico antigo
    markOnlineOnConnect: false,      // não aparecer como online
  });

  sock.ev.on('creds.update', saveCreds);

  // ── Mapeamento LID → telefone real via contacts.upsert ────────────────────
  // O WhatsApp envia esse evento quando sincroniza contatos, incluindo o mapeamento
  // entre LID (@lid) e o JID real com número (@s.whatsapp.net)
  sock.ev.on('contacts.upsert', (contacts) => {
    let novos = 0;
    for (const c of contacts) {
      const phoneJid = c.id || '';
      const lidJid   = c.lid || '';
      if (lidJid && lidJid.endsWith('@lid') && phoneJid && !phoneJid.endsWith('@lid')) {
        const num = phoneJid.split('@')[0].replace(/\D/g, '');
        if (num.length >= 10 && num.length <= 13 && !lidPhoneCache[lidJid]) {
          lidPhoneCache[lidJid] = num;
          novos++;
        }
      }
    }
    if (novos > 0) {
      _salvarLidCache(lidPhoneCache);
      log(`📱 contacts.upsert: ${novos} LID(s) mapeados para telefone`);
    }
  });

  // ── Conexão ────────────────────────────────────────────────────────────────
  sock.ev.on('connection.update', ({ connection, lastDisconnect, qr }) => {
    // Mostrar QR Code no terminal quando necessário
    if (qr) {
      console.log('\n\n📱 ESCANEIE O QR CODE ABAIXO COM O WHATSAPP:\n');
      qrcode.generate(qr, { small: true });
      console.log('\nNo celular: Configurações → Aparelhos Vinculados → Vincular Aparelho\n');
      log('QR Code gerado — aguardando escaneamento...');
    }

    if (connection === 'close') {
      const code = lastDisconnect?.error?.output?.statusCode;
      const reconectar = code !== DisconnectReason.loggedOut;
      log(`Conexão encerrada (código ${code}). Reconectar: ${reconectar}`);
      if (reconectar) {
        setTimeout(iniciarBot, 5000);
      } else {
        log('Sessão encerrada (logout). Delete a pasta auth/ e escaneie o QR novamente.');
        process.exit(1);
      }
    } else if (connection === 'open') {
      log('✅ Conectado ao WhatsApp!');
    }
  });

  // ── Metadados dos grupos (cache) ───────────────────────────────────────────
  sock.ev.on('groups.update', (updates) => {
    for (const u of updates) {
      if (u.subject) grupoCache[u.id] = u.subject;
    }
  });

  // ── Mensagens recebidas ────────────────────────────────────────────────────
  sock.ev.on('messages.upsert', async ({ messages, type }) => {
    if (type !== 'notify') return;

    const config = getConfig();
    const gruposMonitorados = config.grupos || []; // [] = todos

    for (const msg of messages) {
      // Só grupos
      if (!msg.key?.remoteJid || !isJidGroup(msg.key.remoteJid)) continue;
      if (!msg.message) continue;
      if (msg.key.fromMe) continue; // ignorar mensagens próprias

      const jid = msg.key.remoteJid;

      // Nome do grupo (cache)
      if (!grupoCache[jid]) {
        try {
          const meta = await sock.groupMetadata(jid);
          grupoCache[jid] = meta.subject;
        } catch (e) {
          grupoCache[jid] = jid;
        }
      }
      const nomeGrupo = grupoCache[jid];

      // Ignorar grupos bloqueados (moradores, família, etc.)
      if (GRUPOS_BLOQUEADOS.test(nomeGrupo)) continue;

      // Filtrar por grupos monitorados
      if (gruposMonitorados.length > 0) {
        const monitorado = gruposMonitorados.some(g =>
          nomeGrupo.toLowerCase().includes(g.toLowerCase())
        );
        if (!monitorado) continue;
      }

      // Extrair conteúdo
      const m = msg.message;
      const texto = m.conversation
        || m.extendedTextMessage?.text
        || m.imageMessage?.caption
        || m.videoMessage?.caption
        || m.documentMessage?.caption
        || '';

      const temImagem = !!(m.imageMessage || m.videoMessage);

      // Filtro: só salvar se parecer imóvel
      if (!podeSerImovel(texto, temImagem)) continue;

      // Remetente — resolver LIDs (@lid) para número real
      const participante = msg.key.participant || '';
      const isLid = participante.endsWith('@lid');
      const rawNum = participante.split('@')[0].replace(/\D/g, '');
      let contato = (!isLid && rawNum.length >= 10 && rawNum.length <= 13) ? rawNum : '';
      // Tentar resolver LID → número de telefone via metadados do grupo
      if (isLid && !contato) {
        contato = await resolverLid(sock, jid, participante);
      }
      const autor = msg.pushName || (contato || 'Desconhecido');

      // Baixar imagem se houver (com 2 tentativas)
      let imagemPath = null;
      if (m.imageMessage) {
        for (let tentativa = 1; tentativa <= 2; tentativa++) {
          try {
            const buffer  = await downloadMediaMessage(msg, 'buffer', {});
            const imgFile = path.join(IMG_DIR, `${Date.now()}_${contato}.jpg`);
            fs.writeFileSync(imgFile, buffer);
            imagemPath = imgFile;
            log(`🖼️  Imagem salva: ${path.basename(imgFile)}`);
            break;
          } catch (e) {
            log(`⚠️  Erro ao baixar imagem (tentativa ${tentativa}/2): ${e.message}`);
            if (tentativa < 2) await new Promise(r => setTimeout(r, 2000));
          }
        }
      }

      const entrada = {
        msgId:      msg.key.id,          // ← ID único da mensagem (evita duplicatas)
        grupo:      nomeGrupo,
        autor,
        contato,
        // Guardar LID original para resolução posterior via raspar_contatos.js
        _lidJid:    isLid ? participante : undefined,
        texto:      texto.trim(),
        temImagem,
        imagemPath,
        timestamp:  Number(msg.messageTimestamp),
        data:       new Date(Number(msg.messageTimestamp) * 1000)
                      .toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo' }),
        processado: false,
      };

      salvarNaFila(entrada);
      log(`📩 [${nomeGrupo}] ${autor}: ${texto.substring(0, 80).replace(/\n/g,' ')}`);
    }
  });
}

// ─── Iniciar ─────────────────────────────────────────────────────────────────
log('=== Bot iniciando ===');
iniciarBot().catch(err => {
  log(`ERRO FATAL: ${err.message}`);
  process.exit(1);
});
