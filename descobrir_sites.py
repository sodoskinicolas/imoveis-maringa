#!/usr/bin/env python3
"""
descobrir_sites.py
Analisa domínios novos detectados pelo bot (novos_dominios.json) e tenta
configurar raspagem automática para eles.

Fluxo por domínio:
  1. Verifica se já está em sites_extras.json (já configurado)
  2. Busca página principal e testa compatibilidade com Sub100 (AJAX)
  3. Se Sub100 → adiciona a sites_extras.json automaticamente
  4. Se não → usa Claude Sonnet para analisar e gerar config genérica de seletores
  5. Marca domínio como processado em novos_dominios.json

Uso:
    python3 descobrir_sites.py           # processa todos os pendentes
    python3 descobrir_sites.py --dry-run # só mostra, não salva
"""

import json, re, sys, os
from pathlib import Path
from urllib.parse import urlparse, urljoin

BASE_DIR = Path(__file__).parent
NOVOS_DOMINIOS_FILE  = BASE_DIR / "novos_dominios.json"
SITES_EXTRAS_FILE    = BASE_DIR / "sites_extras.json"

DRY_RUN = "--dry-run" in sys.argv

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9",
}

# ─── Helpers ─────────────────────────────────────────────────────────────────

def _api_key():
    env = BASE_DIR / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("ANTHROPIC_API_KEY="):
                return line.split("=",1)[1].strip()
    return os.environ.get("ANTHROPIC_API_KEY","")

def _carregar_json(path, fallback):
    try:
        if Path(path).exists():
            return json.loads(Path(path).read_text('utf-8'))
    except: pass
    return fallback

def _salvar_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), 'utf-8')

def _fetch(url, timeout=15):
    import requests
    try:
        r = requests.get(url, headers=_HEADERS, timeout=timeout, allow_redirects=True)
        if r.status_code == 200 and 'html' in r.headers.get('Content-Type',''):
            return r.text
    except Exception as e:
        print(f"  ⚠️  Erro ao acessar {url}: {e}")
    return None

# ─── Teste Sub100 ─────────────────────────────────────────────────────────────

def _testar_sub100(dominio, url_exemplo):
    """
    Verifica se o site usa o plugin Sub100 (WordPress).
    Retorna dict de config ou None.
    """
    import requests

    # Tentar descobrir a URL de listagem a partir da URL de exemplo
    parsed = urlparse(url_exemplo)
    base = f"{parsed.scheme}://{parsed.netloc}"

    # Candidatos comuns de URL de listagem
    candidatos_listagem = [
        url_exemplo if 'imoveis' in url_exemplo else None,
        f"{base}/imoveis-a-venda",
        f"{base}/imoveis/venda",
        f"{base}/venda",
        f"{base}/imoveis",
    ]
    candidatos_listagem = [u for u in candidatos_listagem if u]

    # Teste do endpoint AJAX Sub100
    ajax_url = f"{base}/wp-content/plugins/sub100/ajax.php"
    try:
        r = requests.get(ajax_url, params={'pagina': 1, 'filtro': '', 'ordem': 'recentes'},
                         headers=_HEADERS, timeout=10)
        if r.status_code == 200 and ('imovel' in r.text.lower() or 'href' in r.text.lower()):
            print(f"  ✅ Sub100 AJAX detectado em {dominio}")
            # Descobrir URL de listagem para o campo "url"
            for url_list in candidatos_listagem:
                html = _fetch(url_list)
                if html and ('imovel' in html.lower() or 'sub100' in html.lower()):
                    return {
                        "url":          url_list,
                        "domain":       dominio,
                        "grupo":        dominio.replace('.com.br','').replace('.com','').title(),
                        "pagina_param": "pagina",
                        "_tipo":        "sub100",
                    }
            # Fallback: usar base
            return {
                "url":          f"{base}/imoveis-a-venda",
                "domain":       dominio,
                "grupo":        dominio.replace('.com.br','').replace('.com','').title(),
                "pagina_param": "pagina",
                "_tipo":        "sub100",
            }
    except:
        pass

    return None

# ─── Análise via Claude ───────────────────────────────────────────────────────

def _extrair_texto_html(html, max_chars=4000):
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        for t in soup(["script","style","nav","footer","noscript"]):
            t.decompose()
        texto = soup.get_text(" ", strip=True)
        texto = re.sub(r'\s{2,}', ' ', texto)
        # Incluir alguns links para detectar padrões de URL
        links = [a.get('href','') for a in soup.find_all('a', href=True)][:30]
        return texto[:max_chars] + "\n\nLINKS: " + " | ".join(links[:30])
    except:
        return html[:max_chars]

def _analisar_com_claude(dominio, url_exemplo, html_listagem):
    """Usa Claude Sonnet para gerar config de raspagem genérica."""
    api_key = _api_key()
    if not api_key:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        texto = _extrair_texto_html(html_listagem)
        prompt = (
            f'Analise este site imobiliário: {dominio}\n'
            f'URL de exemplo: {url_exemplo}\n\n'
            f'CONTEÚDO DA PÁGINA DE LISTAGEM:\n{texto}\n\n'
            f'Retorne SOMENTE JSON válido com a config de raspagem:\n'
            f'{{\n'
            f'  "url_listagem": "URL da página de listagem de imóveis à venda",\n'
            f'  "pagina_param": "nome do parâmetro de paginação (ex: pagina, page, p) ou null se sem paginação",\n'
            f'  "seletor_card": "seletor CSS de um card/item de imóvel (ex: .imovel-card, article.property)",\n'
            f'  "seletor_link": "seletor CSS do link dentro do card",\n'
            f'  "seletor_titulo": "seletor CSS do título",\n'
            f'  "seletor_preco": "seletor CSS do preço",\n'
            f'  "seletor_bairro": "seletor CSS do bairro/localização",\n'
            f'  "seletor_area": "seletor CSS da área",\n'
            f'  "usa_ajax": false,\n'
            f'  "nome_imobiliaria": "nome amigável da imobiliária",\n'
            f'  "observacoes": "notas sobre como raspar este site"\n'
            f'}}'
        )

        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=800,
            messages=[{"role":"user","content":prompt}]
        )
        m = re.search(r'\{[\s\S]*\}', resp.content[0].text)
        if m:
            cfg = json.loads(m.group())
            cfg['domain']  = dominio
            cfg['_tipo']   = 'generico'
            print(f"  🤖 Config gerada por Claude para {dominio}")
            return cfg
    except Exception as e:
        print(f"  ⚠️  Claude API: {e}")
    return None

# ─── Verificar se domínio já existe nos scrapers ─────────────────────────────

_DOMINIOS_RASPADOS = {
    'harakiimoveis.com.br', 'massaruimoveis.com.br', 'bellakaza.com.br',
    'silviobertoli.com.br', 'casadocorretor.com.br',
    'vivareal.com.br', 'zapimoveis.com.br', 'imovelweb.com.br',
    'olx.com.br', 'zap.com.br',
}

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    novos = _carregar_json(NOVOS_DOMINIOS_FILE, {})
    extras = _carregar_json(SITES_EXTRAS_FILE, [])
    dominios_extras = {s['domain'] for s in extras}

    pendentes = {
        dom: info for dom, info in novos.items()
        if not info.get('analisado') and dom not in _DOMINIOS_RASPADOS and dom not in dominios_extras
    }

    if not pendentes:
        print("✅ Nenhum domínio novo para analisar.")
        return

    print(f"🔍 {len(pendentes)} domínio(s) novo(s) para analisar...\n")
    adicionados = 0

    for dominio, info in pendentes.items():
        url_exemplo = info.get('url_exemplo', f'https://{dominio}')
        print(f"── {dominio} ({'exemplo: ' + url_exemplo[:60]})")

        cfg = None

        # 1. Testar Sub100
        cfg = _testar_sub100(dominio, url_exemplo)

        # 2. Se não Sub100, tentar análise genérica via Claude
        if not cfg:
            # Buscar página de listagem (tentar URL de exemplo ou home)
            parsed = urlparse(url_exemplo)
            base = f"{parsed.scheme}://{parsed.netloc}"
            html = _fetch(url_exemplo) or _fetch(f"{base}/imoveis-a-venda") or _fetch(base)
            if html:
                cfg = _analisar_com_claude(dominio, url_exemplo, html)
            else:
                print(f"  ❌ Não consegui acessar {dominio}")

        if cfg:
            print(f"  📋 Config: tipo={cfg.get('_tipo')} | nome={cfg.get('grupo') or cfg.get('nome_imobiliaria')}")
            if not DRY_RUN:
                extras.append(cfg)
                _salvar_json(SITES_EXTRAS_FILE, extras)
                adicionados += 1
                print(f"  ✅ Adicionado a sites_extras.json")
        else:
            print(f"  ❓ Não foi possível gerar config automaticamente — revisar manualmente")

        # Marcar como analisado (mesmo que não tenha gerado config, para não tentar de novo)
        novos[dominio]['analisado'] = True
        novos[dominio]['config_gerada'] = bool(cfg)
        if not DRY_RUN:
            _salvar_json(NOVOS_DOMINIOS_FILE, novos)

        print()

    print(f"\n✅ {adicionados} site(s) adicionado(s) ao raspador automático.")
    if adicionados:
        print("   → Serão raspados no próximo ciclo do GitHub Actions (3h).")

if __name__ == "__main__":
    main()
