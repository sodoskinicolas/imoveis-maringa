/**
 * PASSO 2 — Envia mensagem personalizada para cada corretor
 * Usa Baileys (conexão direta, sem Chrome/Puppeteer)
 * Lê: contatos_corretores.xlsx
 *
 * Uso: node enviar_mensagens.js
 */

const { default: makeWASocket, useMultiFileAuthState, fetchLatestBaileysVersion, DisconnectReason } = require('@whiskeysockets/baileys');
const XLSX = require('xlsx');
const readline = require('readline');
const path = require('path');
const { Boom } = require('@hapi/boom');
const qrcode = require('qrcode-terminal');

const ARQUIVO    = path.join(__dirname, '..', 'contatos_corretores.xlsx');
const AUTH_FOLDER = path.join(__dirname, 'baileys_auth');

// ─── MENSAGEM ─────────────────────────────────────────────────────────────────
const MENSAGEM = (primeiroNome) =>
`Opa! Tudo bem ${primeiroNome || 'tudo bem'}? 😊

Vi que você trabalha com corretagem aqui em Maringá, me conte — tem mais grupos de corretores como esse aqui em Maringá?

Estou mapeando o mercado da região e seria ótimo trocar uma ideia contigo!`;

const DELAY_MIN = 8000;
const DELAY_MAX = 20000;
// ──────────────────────────────────────────────────────────────────────────────

const sleep  = (ms) => new Promise(r => setTimeout(r, ms));
const random = () => Math.floor(Math.random() * (DELAY_MAX - DELAY_MIN + 1)) + DELAY_MIN;

const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
const pergunta = (texto) => new Promise(resolve => rl.question(texto, resolve));

function carregarPlanilha() {
    const wb   = XLSX.readFile(ARQUIVO);
    const ws   = wb.Sheets[wb.SheetNames[0]];
    const dados = XLSX.utils.sheet_to_json(ws);
    return { wb, dados };
}

function salvarPlanilha(wb, dados) {
    const ws = XLSX.utils.json_to_sheet(dados);
    ws['!cols'] = [
        { wch: 20 }, { wch: 30 }, { wch: 20 },
        { wch: 8 },  { wch: 20 }, { wch: 20 }, { wch: 30 }
    ];
    wb.Sheets[wb.SheetNames[0]] = ws;
    XLSX.writeFile(wb, ARQUIVO);
}

async function main() {
    // Verifica planilha
    let wb, dados;
    try {
        ({ wb, dados } = carregarPlanilha());
    } catch {
        console.error(`\n✗ Arquivo não encontrado: ${ARQUIVO}`);
        console.error('Execute primeiro: node extrair_contatos.js');
        process.exit(1);
    }

    const pendentes = dados.filter(r => r['Mensagem Enviada'] !== 'Sim');
    console.log(`\nTotal na planilha: ${dados.length}`);
    console.log(`Pendentes:         ${pendentes.length}\n`);

    if (pendentes.length === 0) {
        console.log('Todas as mensagens já foram enviadas!');
        process.exit(0);
    }

    // Prévia
    const nomeTeste = pendentes[0]['Primeiro Nome'] || 'Corretor';
    console.log('=== PRÉVIA DA MENSAGEM ===');
    console.log(MENSAGEM(nomeTeste));
    console.log('==========================\n');

    const confirma = await pergunta(`Enviar para ${pendentes.length} corretores? (s/n): `);
    if (confirma.toLowerCase() !== 's') {
        console.log('Cancelado.');
        rl.close();
        process.exit(0);
    }

    // Conectar WhatsApp
    const { state, saveCreds } = await useMultiFileAuthState(AUTH_FOLDER);
    const { version } = await fetchLatestBaileysVersion();

    const sock = makeWASocket({
        version,
        auth: state,
        printQRInTerminal: false,
        logger: require('pino')({ level: 'silent' }),
        browser: ['Chatbot Corretores', 'Chrome', '1.0.0'],
    });

    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect, qr } = update;

        if (qr) {
            console.log('\n========================================');
            console.log('  Escaneie o QR Code com seu WhatsApp  ');
            console.log('========================================\n');
            qrcode.generate(qr, { small: true });
        }

        if (connection === 'close') {
            const code = (lastDisconnect?.error instanceof Boom)
                ? lastDisconnect.error.output?.statusCode
                : undefined;
            if (code !== DisconnectReason.loggedOut) {
                console.log('\nReconectando...');
                main();
            }
        }

        if (connection === 'open') {
            console.log('✓ WhatsApp conectado! Iniciando envios...\n');

            let enviados = 0;
            let erros    = 0;

            for (let i = 0; i < dados.length; i++) {
                const contato = dados[i];
                if (contato['Mensagem Enviada'] === 'Sim') continue;

                const numero = String(contato['Número']).trim();
                const pnome  = contato['Primeiro Nome'] || 'Corretor';
                const nome   = contato['Nome Completo'] || numero;
                const jid    = `${numero}@s.whatsapp.net`;
                const texto  = MENSAGEM(pnome);
                const agora  = new Date().toLocaleString('pt-BR');

                process.stdout.write(`[${enviados + erros + 1}/${pendentes.length}] ${nome} (${numero})... `);

                try {
                    await sock.sendMessage(jid, { text: texto });
                    dados[i]['Mensagem Enviada'] = 'Sim';
                    dados[i]['Data Envio']       = agora;
                    enviados++;
                    console.log('✓');
                } catch (err) {
                    dados[i]['Mensagem Enviada'] = 'Erro';
                    dados[i]['Resposta']         = err.message;
                    erros++;
                    console.log(`✗ ${err.message}`);
                }

                salvarPlanilha(wb, dados);

                if (enviados + erros < pendentes.length) {
                    const espera = random();
                    process.stdout.write(`    ⏳ Aguardando ${Math.round(espera/1000)}s...\r`);
                    await sleep(espera);
                }
            }

            console.log(`\n\n=== RESUMO ===`);
            console.log(`✓ Enviados: ${enviados}`);
            console.log(`✗ Erros:    ${erros}`);
            console.log(`Planilha atualizada: ${ARQUIVO}`);

            rl.close();
            process.exit(0);
        }
    });
}

main().catch(err => {
    console.error(err);
    process.exit(1);
});
