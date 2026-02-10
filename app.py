import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import io
import re

# --- CONFIGURAÇÕES DO PERSONAGEM ---
# Nome: Dizimeiro
# Função: Auditor de DIFAL de Entrada (O Cobrador de Fronteira)

# Alíquotas internas atualizadas 2025/2026
ALIQUOTAS_INTERNAS = {
    'AC': 19.0, 'AL': 19.0, 'AM': 20.0, 'AP': 18.0, 'BA': 20.5, 'CE': 20.0, 'DF': 20.0,
    'ES': 17.0, 'GO': 19.0, 'MA': 22.0, 'MG': 18.0, 'MS': 17.0, 'MT': 17.0, 'PA': 19.0,
    'PB': 20.0, 'PE': 20.5, 'PI': 21.0, 'PR': 19.5, 'RJ': 22.0, 'RN': 20.0, 'RO': 19.5,
    'RR': 20.0, 'RS': 17.0, 'SC': 17.0, 'SE': 19.0, 'SP': 18.0, 'TO': 20.0
}

# Estados que exigem Base Dupla (Gross-up) para empresas de Regime Normal
ESTADOS_BASE_DUPLA = ['MG', 'PR', 'RS', 'SC', 'SP', 'BA', 'PE', 'GO', 'MS', 'AL', 'SE']

def limpar_cnpj(texto):
    if pd.isna(texto): return ""
    nums = re.sub(r'\D', '', str(texto))
    return nums[:14] if len(nums) >= 14 else ""

def extrair_dados_xml_agrupados(xml_file):
    """
    Lê o XML e agrupa os valores por CFOP para bater com o Relatório de Entradas.
    Mantém a integridade de todos os impostos de origem e taxas acessórias.
    """
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
        ns = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}
        
        infNfe = root.find('.//nfe:infNFe', ns)
        if infNfe is None: return []

        # Cabeçalho da Nota
        nNF = int(root.find('.//nfe:ide/nfe:nNF', ns).text)
        emit_cnpj = root.find('.//nfe:emit/nfe:CNPJ', ns).text
        emit_nome = root.find('.//nfe:emit/nfe:xNome', ns).text
        dest_cnpj = root.find('.//nfe:dest/nfe:CNPJ', ns).text
        
        # Dicionário para agrupar por CFOP (conforme o relatório do usuário)
        resumo_cfop = {}
        
        for det in root.findall('.//nfe:det', ns):
            prod = det.find('nfe:prod', ns)
            imposto = det.find('nfe:imposto', ns)
            
            cfop = prod.find('nfe:CFOP', ns).text
            vProd = float(prod.find('nfe:vProd', ns).text)
            vIPI = float(imposto.find('.//nfe:vIPI', ns).text) if imposto.find('.//nfe:vIPI', ns) is not None else 0.0
            vFrete = float(prod.find('nfe:vFrete', ns).text) if prod.find('nfe:vFrete', ns) is not None else 0.0
            vOutro = float(prod.find('nfe:vOutro', ns).text) if prod.find('nfe:vOutro', ns) is not None else 0.0
            vSeg = float(prod.find('nfe:vSeg', ns).text) if prod.find('nfe:vSeg', ns) is not None else 0.0
            vDesc = float(prod.find('nfe:vDesc', ns).text) if prod.find('nfe:vDesc', ns) is not None else 0.0
            
            # Valor Contábil (Soma de tudo conforme o relatório de entradas)
            vContabil_item = vProd + vIPI + vFrete + vOutro + vSeg - vDesc
            
            # Dados de ICMS e Origem
            icms_node = imposto.find('.//nfe:ICMS/*', ns)
            origem = icms_node.find('nfe:orig', ns).text if icms_node.find('nfe:orig', ns) is not None else "0"
            pICMS = float(icms_node.find('nfe:pICMS', ns).text) if icms_node.find('nfe:pICMS', ns) is not None else 0.0
            vICMS = float(icms_node.find('nfe:vICMS', ns).text) if icms_node.find('nfe:vICMS', ns) is not None else 0.0
            vICMSST = float(icms_node.find('nfe:vICMSST', ns).text) if icms_node.find('nfe:vICMSST', ns) is not None else 0.0
            
            if cfop not in resumo_cfop:
                resumo_cfop[cfop] = {
                    'Nota': nNF, 'CNPJ_Emit': emit_cnpj, 'Fornecedor': emit_nome,
                    'CNPJ_Dest': dest_cnpj, 'CFOP': cfop, 'V_Contabil_XML': 0.0,
                    'Base_Calculo_DIFAL': 0.0, 'V_ICMS_Origem': 0.0, 'Aliq_Inter': pICMS,
                    'V_ST_Nota': 0.0, 'Origem_Mercadoria': origem
                }
            
            resumo_cfop[cfop]['V_Contabil_XML'] += vContabil_item
            # A base do DIFAL na entrada inclui IPI e despesas acessórias para Uso/Consumo/Ativo
            resumo_cfop[cfop]['Base_Calculo_DIFAL'] += (vProd + vIPI + vFrete + vOutro + vSeg)
            resumo_cfop[cfop]['V_ICMS_Origem'] += vICMS
            resumo_cfop[cfop]['V_ST_Nota'] += vICMSST
            
        return list(resumo_cfop.values())
    except Exception as e:
        return []

def calcular_dizimo(row, regime, uf_destino):
    """Lógica do Dízimeiro para calcular o DIFAL (O pedágio de entrada)"""
    
    # 1. Se já teve ST na nota, o dízimo já foi pago
    if row['V_ST_Nota'] > 0.1:
        return 0.0, "ST Já Recolhida pelo Fornecedor"
    
    # 2. CFOPs de Uso, Consumo ou Ativo Imobilizado
    cfops_obrigatorios = ['1556', '2556', '1407', '2407', '1551', '2551', '1406', '2406']
    if row['CFOP_Limpo'] not in cfops_obrigatorios:
        return 0.0, f"CFOP {row['CFOP_Limpo']} não gera dízimo (DIFAL)"

    aliq_interna = ALIQUOTAS_INTERNAS[uf_destino] / 100
    aliq_origem = row['Aliq_Inter'] / 100

    if regime == "Simples Nacional":
        # Base Única
        valor = row['Base_Calculo_DIFAL'] * (aliq_interna - aliq_origem)
        return round(max(0, valor), 2), "Simples (Base Única)"
    else:
        # Regime Normal
        if uf_destino in ESTADOS_BASE_DUPLA:
            # Base Dupla (Gross-up)
            base_liquida = row['Base_Calculo_DIFAL'] - row['V_ICMS_Origem']
            base_cheia = base_liquida / (1 - aliq_interna)
            valor = (base_cheia * aliq_interna) - row['V_ICMS_Origem']
            return round(max(0, valor), 2), "Normal (Base Dupla)"
        else:
            valor = row['Base_Calculo_DIFAL'] * (aliq_interna - aliq_origem)
            return round(max(0, valor), 2), "Normal (Base Única)"

def main():
    st.set_page_config(page_title="Dizimeiro - Auditor de DIFAL", layout="wide")
    st.title("💰 O Dizimeiro")
    st.subheader("Auditoria de Diferencial de Alíquota de Entrada")
    st.markdown("---")

    with st.sidebar:
        st.header("📜 Configurações do Reino")
        meu_cnpj = st.text_input("Seu CNPJ (Destinatário)", placeholder="Apenas números")
        meu_regime = st.selectbox("Seu Regime Tributário", ["Regime Normal", "Simples Nacional"])
        minha_uf = st.selectbox("Sua UF de Destino", list(ALIQUOTAS_INTERNAS.keys()), index=25) # SP Default
        
    col_a, col_b = st.columns(2)
    with col_a:
        arquivo_csv = st.file_uploader("📂 Suba o Relatório de Entradas (CSV)", type=['csv'])
    with col_b:
        arquivos_xml = st.file_uploader("📁 Suba as Notas Fiscais (XML)", type=['xml'], accept_multiple_files=True)

    if arquivo_csv and arquivos_xml and meu_cnpj:
        # 1. Processar o Relatório (Pulando 5 linhas de cabeçalho padrão)
        df_rel = pd.read_csv(arquivo_csv, sep=';', encoding='latin-1', skiprows=5)
        df_rel = df_rel[df_rel['Nota'].notna() & (~df_rel['Fornecedor'].str.contains('Total', na=False))]
        
        # Normalização para cruzamento
        df_rel['Nota_Rel'] = pd.to_numeric(df_rel['Nota'], errors='coerce')
        df_rel['CFOP_Limpo'] = df_rel['CFOP'].str.replace('-', '').str.strip()
        df_rel['V_Contabil_Rel'] = df_rel['Valor Contábil'].astype(str).str.replace('.', '').str.replace(',', '.').astype(float)
        
        # 2. Processar XMLs
        base_xml = []
        for f in arquivos_xml:
            base_xml.extend(extrair_dados_xml_agrupados(f))
        
        df_xml = pd.DataFrame(base_xml)
        df_xml = df_xml[df_xml['CNPJ_Dest'] == re.sub(r'\D', '', meu_cnpj)]

        if not df_xml.empty:
            # 3. Cruzamento: Nota + CFOP + Valor Contábil
            # Esta tríade garante que o XML agrupado case com a linha do relatório
            df_final = df_xml.merge(
                df_rel[['Nota_Rel', 'CFOP_Limpo', 'V_Contabil_Rel']], 
                left_on=['Nota', 'CFOP'], 
                right_on=['Nota_Rel', 'CFOP_Limpo'], 
                how='inner'
            )

            # 4. Auditoria e Cálculo do Dízimo
            res = df_final.apply(lambda r: calcular_dizimo(r, meu_regime, minha_uf), axis=1, result_type='expand')
            df_final['DIFAL_Recolher'] = res[0]
            df_final['Motivo_Logica'] = res[1]

            st.write("### 📜 Relatório de Auditoria Final")
            cols_exibicao = ['Nota', 'Fornecedor', 'CFOP', 'V_Contabil_XML', 'Aliq_Inter', 'DIFAL_Recolher', 'Motivo_Logica']
            st.dataframe(df_final[cols_exibicao].sort_values(by='DIFAL_Recolher', ascending=False))

            total_difal = df_final['DIFAL_Recolher'].sum()
            st.metric("Total de Dízimo (DIFAL) a Recolher", f"R$ {total_difal:,.2f}")

            # Exportação
            output = io.BytesIO()
            df_final.to_excel(output, index=False, engine='xlsxwriter')
            st.download_button("📥 Baixar Auditoria do Dizimeiro (Excel)", output.getvalue(), "auditoria_dizimeiro.xlsx")
        else:
            st.error("Nenhum XML coincide com o CNPJ informado.")
    elif not meu_cnpj and (arquivo_csv or arquivos_xml):
        st.warning("O Dizimeiro precisa saber o seu CNPJ para começar a cobrança.")

if __name__ == "__main__":
    main()
