/**
 * PASSO 1 — Extrai participantes de um grupo do WhatsApp
 * Usa Baileys (conexão direta, sem Chrome/Puppeteer)
 * Salva em: contatos_corretores.xlsx
 *
 * Uso: node extrair_contatos.js
 */

const { default: makeWASocket, useMultiFileAuthState, fetchLatestBaileysVersion, DisconnectReason } = require('@whiskeysockets/baileys');
const XLSX = require('xlsx');
const readline = require('readline');
const path = require('path');
const { Boom } = require('@hapi/boom');
const qrcode = require('qrcode-terminal');

const ARQUIVO_SAIDA = path.join(__dirname, '..', 'contatos_corretores.xlsx');
const AUTH_FOLDER   = path.join(__dirname, 'baileys_auth');

const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
const pergunta = (texto) => new Promise(resolve => rl.question(texto, resolve));

async function main() {
    const { state, saveCreds } = await useMultiFileAuthState(AUTH_FOLDER);
    const { version } = await fetchLatestBaileysVersion();

    console.log(`\nUsando WhatsApp v${version.join('.')}\n`);

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
            console.log('\nNo celular: WhatsApp → ⋮ → Dispositivos Conectados → Conectar Dispositivo\n');
        }

        if (connection === 'close') {
            const code = (lastDisconnect?.error instanceof Boom)
                ? lastDisconnect.error.output?.statusCode
                : undefined;

            if (code !== DisconnectReason.loggedOut) {
                console.log('Reconectando...');
                main();
            } else {
                console.log('Sessão encerrada. Delete a pasta baileys_auth e tente novamente.');
                process.exit(1);
            }
        }

        if (connection === 'open') {
            console.log('✓ WhatsApp conectado!\n');
            await extrairContatos(sock);
        }
    });
}

async function extrairContatos(sock) {
    try {
        console.log('Buscando grupos...');
        const grupos = await sock.groupFetchAllParticipating();
        const lista  = Object.values(grupos);

        if (lista.length === 0) {
            console.log('Nenhum grupo encontrado.');
            process.exit(0);
        }

        console.log(`\n=== ${lista.length} GRUPOS ENCONTRADOS ===`);
        lista.forEach((g, i) => {
            console.log(`[${i}] ${g.subject} (${g.participants.length} participantes)`);
        });

        const escolha = await pergunta('\nDigite o número do grupo de corretores: ');
        const idx = parseInt(escolha.trim());

        if (isNaN(idx) || idx < 0 || idx >= lista.length) {
            console.log('Número inválido.');
            process.exit(1);
        }

        const grupo = lista[idx];
        console.log(`\nExtraindo participantes de: "${grupo.subject}"...`);

        const registros = grupo.participants
            .filter(p => !p.id.endsWith('@g.us'))
            .map(p => {
                const numero    = p.id.replace('@s.whatsapp.net', '');
                const pushName  = p.notify || '';
                const pnome     = pushName.trim().split(' ')[0] || '';

                return {
                    'Número':           numero,
                    'Nome Completo':    pushName,
                    'Primeiro Nome':    pnome,
                    'Admin':            (p.admin === 'admin' || p.admin === 'superadmin') ? 'Sim' : 'Não',
                    'Mensagem Enviada': 'Não',
                    'Data Envio':       '',
                    'Resposta':         ''
                };
            });

        // Remover duplicatas
        const unicos = registros.filter((r, i, arr) =>
            arr.findIndex(x => x['Número'] === r['Número']) === i
        );

        // Salvar Excel
        const wb = XLSX.utils.book_new();
        const ws = XLSX.utils.json_to_sheet(unicos);
        ws['!cols'] = [
            { wch: 20 }, { wch: 30 }, { wch: 20 },
            { wch: 8 },  { wch: 20 }, { wch: 20 }, { wch: 30 }
        ];
        XLSX.utils.book_append_sheet(wb, ws, 'Corretores');
        XLSX.writeFile(wb, ARQUIVO_SAIDA);

        console.log(`\n✓ ${unicos.length} contatos salvos em:\n  ${ARQUIVO_SAIDA}`);
        console.log('\nPróximo passo: node enviar_mensagens.js');

        // Mostra prévia
        console.log('\nPrimeiros 10:');
        console.table(unicos.slice(0, 10).map(r => ({
            Número: r['Número'],
            Nome:   r['Nome Completo'] || '(sem nome)',
            Admin:  r['Admin']
        })));

    } catch (err) {
        console.error('Erro ao extrair:', err.message);
    } finally {
        rl.close();
        process.exit(0);
    }
}

main().catch(err => {
    console.error(err);
    process.exit(1);
});
