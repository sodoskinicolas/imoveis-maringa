const XLSX = require('xlsx');
const path = require('path');
const fs = require('fs');

const dados = JSON.parse(fs.readFileSync('/tmp/contatos_raw.json', 'utf8'));

const ARQUIVO = path.join(__dirname, '..', 'contatos_corretores.xlsx');
const wb = XLSX.utils.book_new();
const ws = XLSX.utils.json_to_sheet(dados);
ws['!cols'] = [
  { wch: 20 }, { wch: 35 }, { wch: 20 }, { wch: 8 },
  { wch: 10 }, { wch: 20 }, { wch: 20 }, { wch: 30 }
];
XLSX.utils.book_append_sheet(wb, ws, 'Corretores');
XLSX.writeFile(wb, ARQUIVO);
console.log('Salvo: ' + ARQUIVO + ' (' + dados.length + ' contatos)');
