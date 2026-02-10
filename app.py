import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import io
import re
import zipfile

# --- CONFIGURAÇÕES DO PERSONAGEM ---
# Nome: Dizimeiro
# Função: Auditor de DIFAL de Entrada (Com extração recursiva de arquivos ZIP)

ALIQUOTAS_INTERNAS = {
    'AC': 19.0, 'AL': 19.0, 'AM': 20.0, 'AP': 18.0, 'BA': 20.5, 'CE': 20.0, 'DF': 20.0,
    'ES': 17.0, 'GO': 19.0, 'MA': 22.0, 'MG': 18.0, 'MS': 17.0, 'MT': 17.0, 'PA': 19.0,
    'PB': 20.0, 'PE': 20.5, 'PI': 21.0, 'PR': 19.5, 'RJ': 22.0, 'RN': 20.0, 'RO': 19.5,
    'RR': 20.0, 'RS': 17.0, 'SC': 17.0, 'SE': 19.0, 'SP': 18.0, 'TO': 20.0
}

ESTADOS_BASE_DUPLA = ['MG', 'PR', 'RS', 'SC', 'SP', 'BA', 'PE', 'GO', 'MS', 'AL', 'SE']

def extrair_xmls_recursivo(uploaded_file):
    """
    Função 'Matriosca': Abre ZIPs dentro de ZIPs até encontrar arquivos XML.
    """
    xml_contents = []
    
    def process_zip(file_obj):
        try:
            with zipfile.ZipFile(file_obj) as z:
                for name in z.namelist():
                    content = z.read(name)
                    if name.lower().endswith('.xml'):
                        xml_contents.append(io.BytesIO(content))
                    elif name.lower().endswith('.zip'):
                        # Recursividade: se encontrar outro ZIP lá dentro, abre ele
                        process_zip(io.BytesIO(content))
        except zipfile.BadZipFile:
            pass

    # Se o arquivo subido for um ZIP, começa a descascar
    if uploaded_file.name.lower().endswith('.zip'):
        process_zip(uploaded_file)
    # Se for um XML direto, apenas adiciona à lista
    elif uploaded_file.name.lower().endswith('.xml'):
        xml_contents.append(uploaded_file)
        
    return xml_contents

def extrair_dados_xml_agrupados(xml_io):
    try:
        tree = ET.parse(xml_io)
        root = tree.getroot()
        ns = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}
        
        infNfe = root.find('.//nfe:infNFe', ns)
        if infNfe is None: return []

        nNF = int(root.find('.//nfe:ide/nfe:nNF', ns).text)
        emit_cnpj = root.find('.//nfe:emit/nfe:CNPJ', ns).text
        emit_nome = root.find('.//nfe:emit/nfe:xNome', ns).text
        dest_cnpj = root.find('.//nfe:dest/nfe:CNPJ', ns).text
        
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
            
            vContabil_item = vProd + vIPI + vFrete + vOutro + vSeg - vDesc
            
            icms_node = imposto.find('.//nfe:ICMS/*', ns)
            pICMS = float(icms_node.find('nfe:pICMS', ns).text) if icms_node.find('nfe:pICMS', ns) is not None else 0.0
            vICMS = float(icms_node.find('nfe:vICMS', ns).text) if icms_node.find('nfe:vICMS', ns) is not None else 0.0
            vICMSST = float(icms_node.find('nfe:vICMSST', ns).text) if icms_node.find('nfe:vICMSST', ns) is not None else 0.0
            
            if cfop not in resumo_cfop:
                resumo_cfop[cfop] = {
                    'Nota': nNF, 'CNPJ_Emit': emit_cnpj, 'Fornecedor': emit_nome,
                    'CNPJ_Dest': dest_cnpj, 'CFOP': cfop, 'V_Contabil_XML': 0.0,
                    'Base_Calculo_DIFAL': 0.0, 'V_ICMS_Origem': 0.0, 'Aliq_Inter': pICMS,
                    'V_ST_Nota': 0.0
                }
            
            resumo_cfop[cfop]['V_Contabil_XML'] += vContabil_item
            resumo_cfop[cfop]['Base_Calculo_DIFAL'] += (vProd + vIPI + vFrete + vOutro + vSeg)
            resumo_cfop[cfop]['V_ICMS_Origem'] += vICMS
            resumo_cfop[cfop]['V_ST_Nota'] += vICMSST
            
        return list(resumo_cfop.values())
    except:
        return []

def calcular_dizimo(row, regime, uf_destino):
    if row['V_ST_Nota'] > 0.1: return 0.0, "ST Já Recolhida"
    
    cfops_obrigatorios = ['1556', '2556', '1407', '2407', '1551', '2551', '1406', '2406']
    if row['CFOP_Limpo'] not in cfops_obrigatorios:
        return 0.0, f"CFOP {row['CFOP_Limpo']} sem DIFAL"

    aliq_interna = ALIQUOTAS_INTERNAS[uf_destino] / 100
    aliq_origem = row['Aliq_Inter'] / 100

    if regime == "Simples Nacional":
        valor = row['Base_Calculo_DIFAL'] * (aliq_interna - aliq_origem)
        return round(max(0, valor), 2), "Simples (Base Única)"
    else:
        if uf_destino in ESTADOS_BASE_DUPLA:
            base_liquida = row['Base_Calculo_DIFAL'] - row['V_ICMS_Origem']
            base_cheia = base_liquida / (1 - aliq_interna)
            valor = (base_cheia * aliq_interna) - row['V_ICMS_Origem']
            return round(max(0, valor), 2), "Normal (Base Dupla)"
        else:
            valor = row['Base_Calculo_DIFAL'] * (aliq_interna - aliq_origem)
            return round(max(0, valor), 2), "Normal (Base Única)"

def main():
    st.set_page_config(page_title="Dizimeiro - Matriosca Edition", layout="wide")
    st.title("💰 O Dizimeiro")
    st.subheader("Auditoria de DIFAL com Suporte a Arquivos Zipados Recursivos")

    with st.sidebar:
        st.header("📜 Configurações")
        meu_cnpj = st.text_input("Seu CNPJ (Destinatário)")
        meu_regime = st.selectbox("Seu Regime", ["Regime Normal", "Simples Nacional"])
        minha_uf = st.selectbox("Sua UF", list(ALIQUOTAS_INTERNAS.keys()), index=25)

    up_csv = st.file_uploader("📂 Relatório Entradas.csv", type=['csv'])
    up_files = st.file_uploader("📁 XMLs ou ZIPs (Matriosca)", type=['xml', 'zip'], accept_multiple_files=True)

    if up_csv and up_files and meu_cnpj:
        # 1. Processar CSV
        df_rel = pd.read_csv(up_csv, sep=';', encoding='latin-1', skiprows=5)
        df_rel = df_rel[df_rel['Nota'].notna() & (~df_rel['Fornecedor'].str.contains('Total', na=False))]
        df_rel['Nota_Rel'] = pd.to_numeric(df_rel['Nota'], errors='coerce')
        df_rel['CFOP_Limpo'] = df_rel['CFOP'].str.replace('-', '').str.strip()
        
        # 2. Processar XMLs (Descascando a Matriosca)
        base_xml = []
        progress_bar = st.progress(0)
        
        all_xml_ios = []
        for f in up_files:
            all_xml_ios.extend(extrair_xmls_recursivo(f))
            
        for i, xml_io in enumerate(all_xml_ios):
            base_xml.extend(extrair_dados_xml_agrupados(xml_io))
            progress_bar.progress((i + 1) / len(all_xml_ios))
        
        df_xml = pd.DataFrame(base_xml)
        df_xml = df_xml[df_xml['CNPJ_Dest'] == re.sub(r'\D', '', meu_cnpj)]

        if not df_xml.empty:
            # 3. Cruzamento
            df_final = df_xml.merge(df_rel[['Nota_Rel', 'CFOP_Limpo']], left_on=['Nota', 'CFOP'], right_on=['Nota_Rel', 'CFOP_Limpo'], how='inner')
            
            # 4. Cálculo
            res = df_final.apply(lambda r: calcular_dizimo(r, meu_regime, minha_uf), axis=1, result_type='expand')
            df_final['DIFAL_Recolher'] = res[0]
            df_final['Lógica'] = res[1]

            st.write("### 📜 Dízimos Identificados")
            st.dataframe(df_final[['Nota', 'Fornecedor', 'CFOP', 'DIFAL_Recolher', 'Lógica']])
            st.metric("Total a Recolher", f"R$ {df_final['DIFAL_Recolher'].sum():,.2f}")
            
            output = io.BytesIO()
            df_final.to_excel(output, index=False)
            st.download_button("📥 Baixar Relatório", output.getvalue(), "auditoria_dizimeiro.xlsx")
        else:
            st.warning("Nenhum XML encontrado ou CNPJ não confere.")

if __name__ == "__main__":
    main()
