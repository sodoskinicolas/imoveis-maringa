---
name: leitor-grupos-wa
description: >
  Bot que lê mensagens dos grupos do WhatsApp (via WhatsApp Web no Chrome),
  extrai os dados de imóveis/demandas e CATALOGA NO BANCO imoveis.db passando
  pelo pipeline oficial de verificações (processar_mensagens.py). Use quando o
  usuário disser "lê os grupos", "captura imóveis", "atualiza a base", "roda o
  bot", "lê o WhatsApp", "verifica os grupos", ou qualquer variação de
  leitura/captura de imóveis dos grupos de corretores.
---

# Leitor de Grupos WhatsApp → banco imoveis.db (via pipeline com verificações)

Usuário: Nicolas Sodoski, corretor em Maringá.
Objetivo: reler o histórico dos grupos de corretores no **WhatsApp Web** e catalogar
os imóveis/demandas no **`imoveis.db`**.

## PRINCÍPIO CENTRAL (não repita o erro antigo)
NÃO extrair campos (tipo/bairro/preço…) aqui dentro nem gravar em planilha
(`Imoveis_Grupos.xlsx` / `bot_grupos_wa.py` estão APOSENTADOS — inseriam dado cru
pulando as verificações). O caminho correto é:

**texto BRUTO das mensagens → `ingerir_grupos_fila.py` → `mensagens_fila.json` →
`processar_mensagens.py`** (que faz validação de bairro, extração/match de edifício
e condomínio, semântica quartos/suítes, classificação venda-vs-demanda, agrupamento
e deduplicação por fingerprint) **→ `imoveis.db` → `gerar_site.py`.**

A skill só COLETA texto bruto. O pipeline faz o resto.

---

## Passo 0 — Grupos a monitorar
Ler a lista oficial em `~/Claude/Projects/PW/baileys_bot/config.json` (chave `grupos`).
Lista vazia = todos os grupos.

## Passo 1 — Abrir o WhatsApp Web (Chrome MCP)
Usar `mcp__claude-in-chrome__navigate` para `https://web.whatsapp.com` (ou reusar a aba
já aberta via `tabs_context_mcp`). Confirmar login:
```javascript
!!document.querySelector('#pane-side')   // true = logado; false = pedir QR ao usuário
```
Se `false`, avisar o usuário para escanear o QR e parar.

> Observação de sessão: aparelho recém-vinculado só sincroniza ~1 dia de histórico.
> Para backfill profundo, o caminho é o próprio bot (`WA_FULL_HISTORY=1 node bot.js`),
> não esta skill.

## Passo 2 — Abrir cada grupo
Clicar na busca (coord ~[277,86] via `mcp__claude-in-chrome__computer left_click`),
digitar o nome do grupo, aguardar ~1,5s e clicar no primeiro resultado em `#pane-side`.
Confirmar pelo cabeçalho: `document.querySelector('#main header')?.innerText`.

## Passo 3 — Extrair mensagens (método que funciona)
Cada mensagem real tem o atributo **`data-pre-plain-text`** = `"[HH:MM, DD/MM/YYYY] Autor: "`
e o texto em `innerText`. Rolar pra cima acumulando, com este extrator autônomo
(rode via `mcp__claude-in-chrome__javascript_tool`, chame quantas vezes precisar):

```javascript
window.__coleta = window.__coleta || [];
window.__seen   = window.__seen   || new Set();
(async (maxIter=16, cutoffISO='2026-06-30T09:00')=>{
  const cutoff = new Date(cutoffISO).getTime()/1000;          // limite inferior (ajuste)
  const grupo  = document.querySelector('#main header')?.innerText?.split('\n')[0]?.trim() || '???';
  const tsOf = m => { const x=m&&m.match(/\[(\d{2}):(\d{2}), (\d{2})\/(\d{2})\/(\d{4})\]/);
                      return x? new Date(+x[5],+x[4]-1,+x[3],+x[1],+x[2]).getTime()/1000 : null; };
  const scroller = () => { const M=document.querySelector('#main'); let b=null;
    M.querySelectorAll('div').forEach(d=>{ if(d.scrollHeight>d.clientHeight+100 && d.clientHeight>250 && (!b||d.clientHeight>b.clientHeight)) b=d; }); return b; };
  const grab = () => document.querySelectorAll('#main [data-pre-plain-text]').forEach(el=>{
      const meta=el.getAttribute('data-pre-plain-text'); const txt=(el.innerText||'').trim();
      const ts=tsOf(meta); if(!txt||!ts||ts<cutoff) return;
      const key=grupo+'|'+meta+'|'+txt.slice(0,50); if(window.__seen.has(key)) return; window.__seen.add(key);
      const am=meta.match(/\]\s(.+?):\s*$/);
      window.__coleta.push({grupo, autor: am?am[1]:'', texto: txt, timestamp: ts}); });
  const sc=scroller(); grab(); let prev=window.__coleta.length, stag=0;
  for(let i=0;i<maxIter;i++){ if(sc) sc.scrollTop=0; await new Promise(r=>setTimeout(r,900)); grab();
    let oldest=Infinity; for(const c of window.__coleta) if(c.grupo===grupo && c.timestamp<oldest) oldest=c.timestamp;
    if(oldest<=cutoff+60) break;
    const n=window.__coleta.length; if(n===prev){ if(++stag>=5) break; } else stag=0; prev=n; }
  return {grupo, total: window.__coleta.length};
})();
```

Repita a chamada até `oldest` alcançar o corte ou parar de crescer. Passe para o próximo grupo.

## Passo 4 — Exportar o coletado
Ao terminar todos os grupos, pegar `JSON.stringify(window.__coleta)` e salvar em
`~/Claude/Projects/PW/recuperadas_app.json` (lista de `{grupo, autor, texto, timestamp}`;
`contato` opcional).

## Passo 5 — Ingerir no pipeline (aqui acontecem as verificações)
```bash
cd ~/Claude/Projects/PW
python3 ingerir_grupos_fila.py --arquivo recuperadas_app.json --dry-run   # confere quantas entram/duplicam
python3 ingerir_grupos_fila.py --arquivo recuperadas_app.json             # injeta na fila real
python3 processar_mensagens.py                                            # extrai+valida→imoveis.db→site
```
`ingerir_grupos_fila.py` aplica o mesmo prefiltro `PALAVRAS_IMOVEL` do bot, gera `msgId`
determinístico (reprocessar o mesmo histórico não duplica) e grava no formato da fila.
`processar_mensagens.py` faz TODA a verificação e a dedup por fingerprint contra o banco.

## Passo 6 — Relatório
Reportar: grupos lidos, mensagens coletadas, e a saída do `processar_mensagens.py`
(imóveis/demandas novos vs. duplicatas ignoradas).

## Regras
- Nunca extrair campos nem gravar direto no banco a partir da skill — sempre pela ponte.
- Nunca deletar dados; o pipeline só adiciona e deduplica.
- Imagens: esta skill é de TEXTO. Captação de imagens/anúncios com foto é feita ao vivo
  pelo bot Baileys (`bot.js`), não aqui.
