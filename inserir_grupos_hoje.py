#!/usr/bin/env python3
"""
Inserção em lote dos imóveis e demandas capturados dos grupos de WhatsApp
via leitura manual (Chrome/WhatsApp Web) em 2026-07-01.
"""
import sys, hashlib
sys.path.insert(0, "/Users/nicolassodoski/Claude/Projects/PW")
import db
from datetime import date

HOJE = date.today().isoformat()

IMOVEIS = [
    dict(grupo="Maringá Apartamentos", corretor="+55 44 9968-5945", contato="554499685945",
         tipo="Apartamento", bairro="Zona 07", area=68.9, quartos=2, suites=1, vagas=1, preco=588000,
         observacoes="Atto Sette House Club - Rua Benjamin Constant, 492 - Andar 11 - desocupado, pronto pra morar, sacada com churrasqueira"),
    dict(grupo="Maringá Apartamentos", corretor="Carlos Pieroni CRECI 19635", contato="",
         tipo="Apartamento", bairro="Zona 03", area=78, quartos=3, suites=1, vagas=2, preco=879000,
         observacoes="Ed Maison Florence - Rua Neo Alves Martins - desocupado, chaves na mão, móveis planejados, sacada c/churrasqueira, próx Parque do Ingá, 157,40m2 total"),
    dict(grupo="Maringá Apartamentos", corretor="Hugo Sutil CORRETOR MGA", contato="",
         tipo="Apartamento", bairro="Zona 03", area=101, quartos=3, suites=2, vagas=2, preco=1080000,
         observacoes="Villa Toscana - móveis planejados"),
    dict(grupo="Maringá Apartamentos", corretor="+55 44 9856-0608", contato="554498560608",
         tipo="Apartamento", bairro="Zona 01 Centro", area=None, quartos=2, suites=1, vagas=None, preco=None,
         observacoes="Condomínio Villagio DI Italia - Junior Joda - https://juniorjoda.com.br/imovel/43820000190/apartamento-a-venda/maringa-pr-zona-01-centro",
         link="https://juniorjoda.com.br/imovel/43820000190/apartamento-a-venda/maringa-pr-zona-01-centro"),
    dict(grupo="Angariações!", corretor="Nádia Mori CRECI 45572", contato="5544988434630",
         tipo="Apartamento", bairro="Zona 08", area=120, quartos=3, suites=3, vagas=2, preco=1576000,
         observacoes="ED. VISION - andar alto frente, lavabo, sacada gourmet c/churrasqueira. Direitos R$400mil + saldo entrega chaves R$1.176.000,00"),
    dict(grupo="Corretores Maringá", corretor="Fernandes", contato="5544999737202",
         tipo="Casa", bairro="Jardim Monções", area=230, quartos=None, suites=None, vagas=None, preco=1990000,
         observacoes="Rua Pioneiro Francisco Alcalde, 438 - terreno 347m²"),
    dict(grupo="Negócio Fechado Imóveis & Corretores Associados!", corretor="Henrique Araújo", contato="",
         tipo="Sobrado", bairro="Jardim Higienópolis", area=230.51, quartos=3, suites=3, banheiros=5, vagas=4, preco=1200000,
         observacoes="Terreno 263,52m², lavabo, escritório, cozinha planejada, área gourmet, aceita permuta por apartamento menor valor"),
    dict(grupo="Clube de Corretores", corretor="Victor Cardoso", contato="5544991123333",
         tipo="Apartamento", bairro="Zona 01 Centro", area=245, quartos=4, banheiros=4, preco=4899000,
         observacoes="Alto padrão - https://vcbroker.com.br/imovel/apartamento-alto-padrao-a-venda-no-centro-maringa-pr/236",
         link="https://vcbroker.com.br/imovel/apartamento-alto-padrao-a-venda-no-centro-maringa-pr/236"),
    dict(grupo="Corretores Maringá", corretor="Odair", contato="",
         tipo="Casa", bairro="Bom Jardim", area=138, quartos=3, suites=1, banheiros=2, vagas=2, preco=850000,
         observacoes="Terreno 200m², sala pé direito 5m, cozinha mármore, área gourmet, piscina 13m aquecida"),
    dict(grupo="Clube de Corretores", corretor="Victor Cardoso", contato="5544991123333",
         tipo="Casa", bairro="Jardim Paraíso", area=225, quartos=4, banheiros=4, preco=2299000,
         observacoes="Casa em condomínio - https://vcbroker.com.br/imovel/casa-alto-padrao-a-venda-em-maringa-pr/101",
         link="https://vcbroker.com.br/imovel/casa-alto-padrao-a-venda-em-maringa-pr/101"),
    dict(grupo="Clube de Corretores", corretor="Victor Cardoso", contato="5544991123333",
         tipo="Apartamento", bairro="Jardim Aclimação", area=55, quartos=2, banheiros=1, preco=449000,
         observacoes="Apartamento novo ao lado da Unicesumar - https://vcbroker.com.br/imovel/apartamento-a-venda-ao-lado-do-unicesumar-maringa-pr/231",
         link="https://vcbroker.com.br/imovel/apartamento-a-venda-ao-lado-do-unicesumar-maringa-pr/231"),
    dict(grupo="Corretores Maringá", corretor="Fernandes", contato="5544999737202",
         tipo="Terreno", bairro="Av. Morangueira", area=3291, preco=6600000,
         observacoes="Terreno comercial em frente à AFMM, próx contorno norte, 1162m² de construção, locação média R$15mil, aceita 50% permuta"),
    dict(grupo="Corretores Maringá", corretor="Fernando", contato="5544999737202",
         tipo="Casa", bairro="Jardim Itália", area=167.75, suites=2, preco=799000,
         observacoes="Terreno 189,75m², piscina aquecida, solar fotovoltaica, área gourmet, ar-condicionado, escritório, móveis planejados, aceita troca por veículos. De 825mil por 799mil"),
    dict(grupo="CASAS - MARINGÁ", corretor="Cláudio", contato="",
         tipo="Casa", bairro="Jardim Espanha", area=125, quartos=3, suites=1, vagas=2, preco=700000,
         observacoes="Terreno 200m², acabamento alto padrão, financia/aceita parte em imóvel ou veículo"),
    dict(grupo="CASAS - MARINGÁ", corretor="+55 44 9935-2809", contato="554499352809",
         tipo="Cobertura", bairro="Zona (Av. Cerro Azul)", area=154, suites=3, vagas=3, preco=2500000,
         observacoes="Cobertura Duplex Tropical Summer - Av Cerro Azul próx Muffato Gourmet - 295m² total, terraço c/jacuzzi, lazer completo, condomínio R$1.600. Aceita permuta casas região sul até 1.5mi"),
    dict(grupo="CASAS - MARINGÁ", corretor="Alisson", contato="",
         tipo="Terreno", bairro="Ebenezer/Novo Alvorada", area=324, preco=226800,
         observacoes="Rodolpho Bernardi, testada 12m, R$700/m², terreno plano, estuda carro como parte de pagamento"),
    dict(grupo="CASAS - MARINGÁ", corretor="Eng.", contato="",
         tipo="Terreno", bairro="Jardim Cidade Monções", area=513.41, preco=845000,
         observacoes="Rua Francisco Knabben 101, medidas 12,71x40,51m, próx Av. Carlos Borges"),
    dict(grupo="CASAS - MARINGÁ", corretor="Hugo Sutil CORRETOR MGA", contato="",
         tipo="Casa", bairro="Jardim Liberdade", area=192, quartos=3, suites=1, preco=945000,
         observacoes="Rua Procópio Ferreira, 554 - terreno 450m², ateliê, lavanderia, churrasqueira, espaço para piscina"),
    dict(grupo="CASAS - MARINGÁ", corretor="+55 44 9968-5945", contato="554499685945",
         tipo="Sobrado", bairro="Jardim Liberdade", area=225, quartos=3, suites=1, vagas=2, preco=1140000,
         observacoes="Sobrado mobiliado, pronto pra morar a partir de 30/06, energia solar, espaço gourmet, monitoramento por câmeras, 1 suíte com jacuzzi"),
    dict(grupo="CASAS - MARINGÁ", corretor="Fernandes", contato="5544999737202",
         tipo="Casa", bairro="Jardim Imperador", area=105, quartos=3, suites=1, preco=550000,
         observacoes="Rua Olinto Mariane, 293 - terreno 150m², pé direito alto, aceita financiamento"),
    dict(grupo="CASAS - MARINGÁ", corretor="Fernandes", contato="5544999737202",
         tipo="Casa", bairro="Parque Itaipu", area=105, quartos=3, suites=1, preco=595000,
         observacoes="Rua Jose da Silva Pedra, 269 - terreno 150m², cozinha moderna, churrasqueira, aquecimento solar, cerca elétrica, aceita financiamento/carro/consórcio"),
    dict(grupo="CASAS - MARINGÁ", corretor="Évora Consultoria Imobiliária", contato="",
         tipo="Sobrado", bairro="Zona 08", area=None, preco=None,
         observacoes="Ref 55220000050 - https://evoraimoveismaringa.com.br/imovel/55220000050/venda/sobrados-em-maringa-pr/zona-08",
         link="https://evoraimoveismaringa.com.br/imovel/55220000050/venda/sobrados-em-maringa-pr/zona-08"),
    dict(grupo="Imoveis Maringá e Região", corretor="Fernando", contato="5544999737202",
         tipo="Casa", bairro="Jardim Alvorada", area=191, quartos=3, suites=1, vagas=3, preco=570000,
         observacoes="Rua Alameda Dr. João Paulinho, próx Praça Farroupilha, uso comercial/residencial, terreno 250m², dispensa fundos, lavabo. De 599mil por 570mil"),
    dict(grupo="Clube de Corretores", corretor="Afonso Leite", contato="5544991735293",
         tipo="Casa", bairro="Jardim Paulista", area=95, quartos=3, suites=1, vagas=2, preco=460000,
         observacoes="Jd Paulista I parte alta, terreno 150m², área gourmet c/churrasqueira, lavanderia - https://pr.olx.com.br/regiao-de-maringa/imoveis/casa-nova-1-suite-3-quartos-jd-paulista-maringa-1513512591",
         link="https://pr.olx.com.br/regiao-de-maringa/imoveis/casa-nova-1-suite-3-quartos-jd-paulista-maringa-1513512591"),
    dict(grupo="Casas Novas a Venda - Eng. Gabriel", corretor="Eng. Gabriel", contato="",
         tipo="Casa", bairro="Jardim Campo Belo", area=55.5, quartos=2, preco=360000,
         observacoes="Opção MCMV, próx Coca Cola, terreno 150m²"),
    dict(grupo="INNOVARE", corretor="Nicolas Sodoski", contato="",
         tipo="Apartamento", bairro="Montalcino", area=None, quartos=3, suites=3, preco=1500000,
         observacoes="Angariação própria - aceita permuta"),
    dict(grupo="Clube de Corretores", corretor="+55 44 9938-4349", contato="554499384349",
         tipo="Casa", bairro="Jardim Novo Oásis", area=90, quartos=3, suites=1, preco=370000,
         observacoes="Casa geminada, recém reformada, próx Av Tuiuti - Ref CA8217 - https://www.winnerbrokers.com.br/imovel/casa-maringa-3-quartos-90-m/CA8217-AKIA",
         link="https://www.winnerbrokers.com.br/imovel/casa-maringa-3-quartos-90-m/CA8217-AKIA"),
    dict(grupo="Clube de Corretores", corretor="+55 44 9938-4349", contato="554499384349",
         tipo="Casa", bairro="Parque Residencial Eldorado", area=105, quartos=3, banheiros=1, vagas=1, preco=365000,
         observacoes="Imóvel de esquina, terreno 250m², próx Acema e Sup. Condor - Ref CA13453 - http://imobiliariaaki.com.br/imovel/detalhes/CA13453-AKIA",
         link="http://imobiliariaaki.com.br/imovel/detalhes/CA13453-AKIA"),
    dict(grupo="Negócio Fechado Imóveis & Corretores Associados!", corretor="Diana Silva CRECI J10781", contato="5544984549471",
         tipo="Terreno", bairro="Condomínio Florais do Lago", area=420, preco=231000,
         observacoes="Lotes a partir de 420m², últimas unidades"),
    dict(grupo="Negócio Fechado Imóveis & Corretores Associados!", corretor="Fatima Imóveis", contato="",
         tipo="Apartamento", bairro="Zona 01 Centro", area=None, quartos=4, suites=2, preco=1600000,
         observacoes="Condomínio Residencial Max Eidam - https://fatimaimoveis.com.br/imovel/55320000045/apartamento-a-venda/maringa-pr-zona-01-centro",
         link="https://fatimaimoveis.com.br/imovel/55320000045/apartamento-a-venda/maringa-pr-zona-01-centro"),
    dict(grupo="Negócio Fechado Imóveis & Corretores Associados!", corretor="+55 44 9928-5459", contato="554499285459",
         tipo="Casa", bairro="Jardim São Clemente", area=85, quartos=3, suites=1, preco=485000,
         observacoes="Rua Pioneira Guilhermina Genebra Garbieri, 332 - terreno 275m², mobiliada, gramado, energia fotovoltaica, motivo mudança de cidade, não aceita permuta"),
    dict(grupo="Corretores parceiros MGA", corretor="+55 44 9811-1647", contato="554498111647",
         tipo="Casa", bairro="Tuiuti", area=85, quartos=3, suites=1, banheiros=1, vagas=2, preco=440000,
         observacoes="Terreno 150m², entra MCMV, toda porcelanato, saídas para ar-condicionado, aceita proposta"),
    dict(grupo="Corretores parceiros MGA", corretor="+55 44 9811-1647", contato="554498111647",
         tipo="Casa", bairro="", area=99, quartos=3, suites=1, preco=380000,
         observacoes="Casa dupla: frente 99m² útil (1 suíte+2 quartos) + casa fundo 70m² útil (2 quartos, alugada), terreno total 300m², falta desmembrar, aceita proposta"),
]

DEMANDAS = [
    dict(grupo="BUSCA DE IMÓVEIS", corretor="+55 44 9886-0181", contato="554498860181",
         tipo_buscado="Apartamento", bairro_regiao="", orcamento_max=380000,
         observacoes="Sem ser MRV, mobiliado"),
    dict(grupo="BUSCA DE IMÓVEIS", corretor="giu", contato="",
         tipo_buscado="Apartamento", bairro_regiao="Condomínio SKY", orcamento_max=None,
         observacoes="Andar 6 ao 17, de preferência"),
    dict(grupo="BUSCA DE IMÓVEIS", corretor="+55 44 9886-0181", contato="554498860181",
         tipo_buscado="Apartamento", bairro_regiao="Centro", orcamento_max=450000,
         observacoes="Andar baixo"),
    dict(grupo="BUSCA DE IMÓVEIS", corretor="Leticia Mendes Corretora", contato="",
         tipo_buscado="Apartamento", bairro_regiao="Spazio Medellín/Mendoza/Montecarlo ou Alvorada", orcamento_max=330000,
         observacoes="Penúltimo/último andar, sol da manhã, sacada, cozinha e quarto do casal planejados"),
    dict(grupo="BUSCA DE IMÓVEIS", corretor="Vagner Souza", contato="",
         tipo_buscado="Apartamento", bairro_regiao="Edifício Maurício Schumann", orcamento_max=None,
         observacoes="Térreo ou 1º andar"),
    dict(grupo="BUSCA DE IMÓVEIS", corretor="Fernandes", contato="5544999737202",
         tipo_buscado="Casa", bairro_regiao="Ney Braga", orcamento_max=400000,
         observacoes="Aceita financiamento"),
    dict(grupo="BUSCA DE IMÓVEIS", corretor="+55 44 9114-3431", contato="554491143431",
         tipo_buscado="Casa", bairro_regiao="Parque da Gávea", orcamento_max=320000,
         observacoes="Documentação ok"),
    dict(grupo="BUSCA DE IMÓVEIS", corretor="+55 44 9935-2809", contato="554499352809",
         tipo_buscado="Terreno", bairro_regiao="Zona 03/Zona 07", orcamento_max=None,
         observacoes="600m², frente maior que 15m, cliente busca permutar, avalia % conforme ação do terreno"),
    dict(grupo="BUSCA DE IMÓVEIS", corretor="Guilherme Pastoril", contato="",
         tipo_buscado="Casa", bairro_regiao="Jardim Monte Rei", orcamento_max=450000,
         observacoes="Casa nova, cliente quer visitar amanhã, urgente"),
    dict(grupo="Angariações!", corretor="+55 44 9968-5945", contato="554499685945",
         tipo_buscado="Apartamento", bairro_regiao="Zona 01", orcamento_max=1600000,
         observacoes="Acima de 100m², 2 vagas de garagem"),
    dict(grupo="Angariações!", corretor="+55 44 9968-5945", contato="554499685945",
         tipo_buscado="Casa", bairro_regiao="Região Sul", orcamento_max=1000000,
         observacoes="Casa térrea, aceita permuta terreno Jardim Monções 300m² (R$500.000)"),
    dict(grupo="CASAS - MARINGÁ", corretor="+55 44 9102-5252", contato="554491025252",
         tipo_buscado="Casa", bairro_regiao="Ney Braga, Hortência ou Olímpico", orcamento_max=400000,
         observacoes="Faixa 350-400 mil"),
    dict(grupo="PARCEIROS PRONTOS PATRIMÔNIO MGA", corretor="José AP902 Villagio", contato="",
         tipo_buscado="Apartamento", bairro_regiao="Acima da Av. Colombo", orcamento_max=600000,
         observacoes="Pretende deixar locado"),
]


def slug_demanda(item):
    base = f"{item.get('corretor')}|{item.get('tipo_buscado')}|{item.get('bairro_regiao')}|{item.get('orcamento_max')}"
    return hashlib.md5(base.encode()).hexdigest()


def main():
    db.init_db()
    conn = db.get_conn()

    inseridos, duplicados = 0, 0
    for item in IMOVEIS:
        item = dict(item)
        item.setdefault("data_captura", HOJE)
        item.setdefault("data_publicacao", HOJE)
        item.setdefault("status", "Novo")
        for campo in ("area", "quartos", "suites", "banheiros", "vagas", "preco", "contato",
                      "observacoes", "link", "nome"):
            item.setdefault(campo, None)
        ok = db.inserir_imovel(conn, item)
        if ok:
            inseridos += 1
        else:
            duplicados += 1
    conn.commit()

    fps_existentes = db.carregar_fps_demandas(conn)
    dem_inseridas, dem_duplicadas = 0, 0
    for item in DEMANDAS:
        item = dict(item)
        item.setdefault("data", HOJE)
        item.setdefault("status", "Ativo")
        for campo in ("area_min", "quartos", "suites", "banheiros", "vagas", "orcamento_max", "contato"):
            item.setdefault(campo, None)
        fp = slug_demanda(item)
        if fp in fps_existentes:
            dem_duplicadas += 1
            continue
        ok = db.inserir_demanda(conn, item, fp)
        if ok:
            dem_inseridas += 1
            fps_existentes.add(fp)
        else:
            dem_duplicadas += 1
    conn.commit()

    print(f"IMOVEIS: {inseridos} inseridos, {duplicados} duplicados (de {len(IMOVEIS)} capturados)")
    print(f"DEMANDAS: {dem_inseridas} inseridas, {dem_duplicadas} duplicadas (de {len(DEMANDAS)} capturadas)")


if __name__ == "__main__":
    main()
