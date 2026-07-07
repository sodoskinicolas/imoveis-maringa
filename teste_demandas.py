#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bateria de regressão da EXTRAÇÃO DE DEMANDAS.

Casos reais capturados da fila do WhatsApp (mensagens_fila.json) com os valores
CORRETOS esperados de extração. Roda só as funções puras de processar_mensagens
(sem rede/DB pesado), comparando o que o extrator devolve com o gabarito.

Uso:
    python3 teste_demandas.py            # roda tudo, mostra só falhas + placar
    python3 teste_demandas.py -v         # mostra todos os casos

Regra do gabarito:
    - chave presente com valor  → campo DEVE ser igual (números) ou CONTER (listas/bairro)
    - chave presente com None   → campo DEVE ser vazio/None
    - chave ausente             → não checa
Para 'bairro'/'edificio' o valor esperado é uma lista de substrings que TODAS
devem aparecer no resultado (ordem livre).
"""
import sys, importlib.util

spec = importlib.util.spec_from_file_location('pm', 'processar_mensagens.py')
pm = importlib.util.module_from_spec(spec)
sys.argv = ['pm']
spec.loader.exec_module(pm)

VERBOSE = '-v' in sys.argv

# ─────────────────────────────────────────────────────────────────────────────
# GABARITO — casos reais + valores corretos
# ─────────────────────────────────────────────────────────────────────────────
CASOS = [
    # (id, texto, esperado)
    ("D01", "Bom dia, pessoal!   Cliente aprovado em 255 mil buscando apartamento Marau, marape, maragogi de 49 m2",
     dict(classe='demanda', tipo='Apartamento', preco=255000, area=49)),

    ("D02", "Bom dia   Cliente busca casa na zona 2 Até 600 mil  01 suíte + 02 quartos  De preferência espaço pra 2 garagens",
     dict(classe='demanda', tipo='Casa', bairro=['Zona 02'], preco=600000, suites=1, quartos=2, vagas=2)),

    ("D03", "Boa tardeeee ☀️   Cliente comprador 🚨  Preciso de apartamento: - metragem: acima 105m2, - semi mobiliado,  - valor investimento: 1 milhão",
     dict(classe='demanda', tipo='Apartamento', area=105, preco=1000000)),

    ("D04", "Boa tarde\n\nPreciso de uma casa ,,, \n\nSemi mobiliado \n\nGaragem pra 4 veículos... \n\nNa região do fim da picada ,,, \n\nFaixa 2.800 a 3.200",
     dict(classe='demanda', tipo='Casa', vagas=4, bairro=['fim da picada'], locacao=True)),

    ("D05", "Pessoal,  Alguém com um VISION pra venda, de preferência que pegue outro apartamento de menor valor , na faixa de R$800mil no negócio? Chama no privado",
     dict(classe='demanda', edificio=['Vision'], preco=800000)),

    ("D06", "Boa tarde\nProcuro terreno acima de 1000 metros na Avenida Nildo Ribeiro",
     dict(classe='demanda', tipo='Terreno', area=1000, bairro=['Nildo Ribeiro'])),

    ("D07", "Pessoal  Alguém com apartamento com acessibilidade de 100m² ??  Enviar no PV por favor",
     dict(classe='demanda', tipo='Apartamento', area=100)),

    ("D08", "Cliente procura casa na regiao do Dias ate 480 mil Nova   Para visitar amanhã de manhã",
     dict(classe='demanda', tipo='Casa', bairro=['Dias'], preco=480000)),

    ("D09", "⚠️⚠️Procuro apartamento de *até R$ 750.000,00*, localizado nas Zonas 01, 03, 04, 07 ou 08.\n\nO imóvel deve ser novo. O proprietário deve aceitar como parte do pagamento uma Toyota Hilux avaliada em R$ 350.000,00, mais R$ 400.000,00 para pagamento em abril de 2027.",
     dict(classe='demanda', tipo='Apartamento', preco=750000,
          bairro=['Zona 01', 'Zona 03', 'Zona 04', 'Zona 07', 'Zona 08'])),

    ("D10", "Boa noite !!    Alguém com NEST635 de 119m2 de preferência sem piscina ?",
     dict(classe='demanda', edificio=['NEST635'], area=119)),

    ("D11", "Apartamento próximo ao centro até 450 mil andar baixo",
     dict(classe='demanda', tipo='Apartamento', bairro=['Centro'], preco=450000)),

    ("D12", "Bom dia! Alguém tem apartamento na zona 07 próximo a Brioche Crocante  Até 500 mil, acima de 80m² com garagem que caiba uma caminhonete",
     dict(classe='demanda', tipo='Apartamento', bairro=['Zona 07'], preco=500000, area=80)),

    ("D13", "Apartamento até 380 mil sem ser Mrv mobiliado",
     dict(classe='demanda', tipo='Apartamento', preco=380000)),

    ("D14", "*Tenho cliente para permutar Maison Constantine 179m² mobiliado* andar alto *por Maison Infinity* (preferência sem mobilia), quem tiver me envie no privado",
     dict(classe='demanda', edificio=['Maison Constantine'], area=179)),

    ("D15", "Procuro apartamento no SKY  tem que ser do andar 6 ao 17, de preferência.  Enviar no particular, por favor!",
     dict(classe='demanda', edificio=['SKY'])),

    ("D16", "Demanda Urgente! \n\n*Para visitar amanhã.*\n\nPreciso de casa na região da mandacaru, não quer muito para baixo.\n\n3 dormitórios, sendo um Suite. Casa boa que não demanda reforma.\n\nValor limite para fechamento é de 420.000.\n\n*Pagamento a vista 🤑*",
     dict(classe='demanda', tipo='Casa', bairro=['Mandacaru'], quartos=3, suites=1, preco=420000)),

    ("D17", "Bom dia. Alguém tem apartamento no SIGNATURE, andar alto?",
     dict(classe='demanda', edificio=['Signature'])),

    ("D18", "Alguém tem apartamento em: Libert Park, Santa Inês, Santa Isabel, Bellagio, Rio Tevere, Torre Oregon, Farol Alexandria?",
     dict(classe='demanda', tipo='Apartamento',
          edificio=['Libert Park', 'Bellagio', 'Rio Tevere', 'Torre Oregon'])),

    ("D19", "Busco apto com 3 quartos, até 400mil, preferencia com planejados",
     dict(classe='demanda', tipo='Apartamento', quartos=3, preco=400000)),

    ("D20", "Boa noite..\n\nPessoal preciso de apartamento com sacada acima do 5° andar, preferência com algum planejado\n\n*Spazio Mendoza*\n\nOu outro que tenha sacada ali na avenida das indústrias.",
     dict(classe='demanda', tipo='Apartamento', edificio=['Spazio Mendoza'])),

    ("D21", "Bom dia, preciso de casa até R$400.000,00 pode ser qualquer região.",
     dict(classe='demanda', tipo='Casa', preco=400000)),

    ("D22", "Oi pessoal se alguém tiver casa região sul \nPreferência Jd São Silvestre \nAté 1.500 locação \nMe avise que passo o cliente",
     dict(classe='demanda', tipo='Casa', bairro=['São Silvestre'], locacao=True)),

    # ── GUARDAS: anúncios de VENDA que NÃO podem virar demanda ────────────────
    ("V01", "🏡🏡 CASA NOVA NA REGIÃO NORTE JD. 3 LAGOAS 🏡🏡   - Se vc procura uma casa nova com um belo quintal nos fundos. Achou😁",
     dict(classe='venda')),
    ("V02", "Apartamento à Venda - Spazio MonteCarlo - Maringá/PR.  Excelente oportunidade para quem busca praticidade, conforto e ótima localização",
     dict(classe='venda')),
    ("V03", "*SOLARIS CLUB RESIDENCE.*  Apartamento em andar alto, com móveis planejados e sacada gourmet. Ideal para quem busca boa localização",
     dict(classe='not_demanda')),
]

# ─────────────────────────────────────────────────────────────────────────────
def extrair(texto):
    """Extração leve para teste: funções puras, sem DB/rede de completar specs."""
    classe = pm.classificar(texto)
    eh_dem = (classe == 'demanda')
    r = {
        'classe': classe,
        'tipo':   pm.extrair_tipo(texto),
        'bairro': pm.extrair_bairro(texto, todos=eh_dem),
        'area':   pm.extrair_area(texto),
        'quartos': pm.extrair_num(texto, [r'quartos?', r'dormit[oó]rios?', r'dorm\.?']),
        'suites':  pm.extrair_suites(texto) if hasattr(pm, 'extrair_suites')
                   else pm.extrair_num(texto, [r'su[íi]tes?']),
        'vagas':   pm.extrair_vagas(texto) if hasattr(pm, 'extrair_vagas')
                   else pm.extrair_num(texto, [r'vagas?', r'garagens?']),
        'preco':   pm.extrair_preco(texto),
    }
    r['edificio'] = (pm.extrair_edificio(texto, todos=True)
                     if 'todos' in pm.extrair_edificio.__code__.co_varnames
                     else pm.extrair_edificio(texto))
    r['locacao'] = pm.eh_locacao(texto) if hasattr(pm, 'eh_locacao') else None
    return r

def checar(esperado, got):
    erros = []
    for k, v in esperado.items():
        if k == 'classe':
            if v == 'demanda' and got['classe'] != 'demanda':
                erros.append(f"classe={got['classe']} (esperava demanda)")
            elif v == 'venda' and got['classe'] != 'venda':
                erros.append(f"classe={got['classe']} (esperava venda)")
            elif v == 'not_demanda' and got['classe'] == 'demanda':
                erros.append(f"classe=demanda (não devia ser demanda)")
            continue
        g = got.get(k)
        if v is None:
            if g not in (None, '', 0):
                erros.append(f"{k}={g!r} (esperava vazio)")
        elif k in ('bairro', 'edificio'):
            hay = str(g or '').lower()
            faltando = [s for s in v if s.lower() not in hay]
            if faltando:
                erros.append(f"{k}={g!r} falta {faltando}")
        elif k == 'locacao':
            if bool(g) != bool(v):
                erros.append(f"locacao={g!r} (esperava {v})")
        else:
            if g != v:
                erros.append(f"{k}={g!r} (esperava {v})")
    return erros

def main():
    ok = 0
    falhas = []
    for cid, texto, esp in CASOS:
        got = extrair(texto)
        erros = checar(esp, got)
        if erros:
            falhas.append((cid, texto, erros, got))
        else:
            ok += 1
        if VERBOSE:
            status = '✅' if not erros else '❌'
            print(f"{status} {cid}: {texto[:70].replace(chr(10),' ')}")
            if erros:
                for e in erros:
                    print(f"      · {e}")
    print("\n" + "=" * 60)
    print(f"PLACAR: {ok}/{len(CASOS)} passaram, {len(falhas)} falharam")
    if falhas and not VERBOSE:
        print("\nFALHAS:")
        for cid, texto, erros, got in falhas:
            print(f"\n❌ {cid}: {texto[:80].replace(chr(10),' ')}")
            for e in erros:
                print(f"      · {e}")
    return 0 if not falhas else 1

if __name__ == '__main__':
    sys.exit(main())
