import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import io
import re
import zipfile
import unicodedata

# --- CONFIGURAÇÕES DO PERSONAGEM ---
# Nome: Dizimeiro (Versão Anti-Erro de Conversão)

ALIQUOTAS_INTERNAS = {
    'AC': 19.0, 'AL': 19.0, 'AM': 20.0, 'AP': 18.0, 'BA': 20.5, 'CE': 20.0, 'DF': 20.0,
    'ES': 17.0, 'GO': 19.0, 'MA': 22.0, 'MG': 18.0, 'MS': 17.0, 'MT': 17.0, 'PA': 19.0,
    'PB': 20.0, 'PE': 20.5, 'PI': 21.0, 'PR': 19.5, 'RJ': 22.0, 'RN': 20.0, 'RO': 19.5,
    'RR': 20.0, 'RS': 17.0, 'SC': 17.0, 'SE': 19.0, 'SP': 18.0, 'TO': 20.0
}

ESTADOS_BASE_DUPLA = ['MG', 'PR', 'RS', 'SC', 'SP', 'BA', 'PE', 'GO', 'MS', 'AL', 'SE']

def normalizar_texto(txt):
    if pd.isna(txt): return ""
    txt = str(txt)
    txt = unicodedata.normalize('NFKD', txt).encode('ASCII', 'ignore').decode('ASCII')
    return txt.upper().strip()

def limpar_cnpj(texto):
    if pd.isna(texto): return ""
    return re.sub(r'\D', '', str(texto)).strip()

def converter_valor_ptbr(valor_str):
    """Converte strings no formato 1.234,56 ou 'Valor Contabil' para float com segurança"""
    if pd.isna(valor_str) or valor_str == "": return 0.0
    v = str(valor_str).strip()
    # Se a string contiver letras (como o nome da coluna), retorna 0 para ser ignorado
    if re.search('[a-zA-Z]', v): return 0.0
    try:
        # Se tiver ponto e vírgula (formato BR: 1.234,56)
        if ',' in v and '.' in v:
            v = v.replace('.', '').replace(',', '.')
        # Se tiver apenas vírgula (formato: 1234,56)
        elif ',' in v:
            v = v.replace(',', '.')
        return float(v)
    except:
        return 0.0

def extrair_xmls_recursivo(uploaded_file):
    xml_contents = []
    def process_zip(file_obj):
        try:
            with zipfile.ZipFile(file_obj) as z:
                for name in z.namelist():
                    if name.startswith('__MACOSX'): continue 
                    content = z.read(name)
                    if name.lower().endswith('.xml'):
                        xml_contents.append(io.BytesIO(content))
                    elif name.lower().endswith('.zip'):
                        process_zip(io.BytesIO(content))
        except: pass

    if uploaded_file.name.lower().endswith('.zip'):
        process_zip(uploaded_file)
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

        ide = root.find('.//nfe:ide', ns)
        nNF = int(ide.find('nfe:nNF', ns).text)
        
        emit = root.find('.//nfe:emit', ns)
        emit_cnpj = emit.find('nfe:CNPJ', ns).text
        emit_nome = emit.find('nfe:xNome', ns).text
        
        dest = root.find('.//nfe:dest', ns)
        dest_cnpj = dest.find('nfe:CNPJ', ns).text if dest.find('nfe:CNPJ', ns) is not None else ""
        
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
            pICMS = float(icms_node.find('nfe:pICMS', ns).text) if icms_node is not None and icms_node.find('nfe:pICMS', ns) is not None and icms_node.find('nfe:pICMS', ns).text else 0.0
            vICMS = float(icms_node.find('nfe:vICMS', ns).text) if icms_node is not None and icms_node.find('nfe:vICMS', ns) is not None and icms_node.find('nfe:vICMS', ns).text else 0.0
            vICMSST = float(icms_node.find('nfe:vICMSST', ns).text) if icms_node is not None and icms_node.find('nfe:vICMSST', ns) is not None and icms_node.find('nfe:vICMSST', ns).text else 0.0
            
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
    try:
        if row['V_ST_Nota'] > 0.1: return 0.0, "ST Já Recolhida"
        cfops_difal = ['1556', '2556', '1407', '2407', '1551', '2551', '1406', '2406']
        cfop_limpo = str(row['CFOP_Limpo'])
        if cfop_limpo not in cfops_difal: return 0.0, "Não sujeito"
        
        aliq_int = ALIQUOTAS_INTERNAS[uf_destino] / 100
        aliq_ori = row['Aliq_Inter'] / 100
        
        if regime == "Simples Nacional":
            val = row['Base_Calculo_DIFAL'] * (aliq_int - aliq_ori)
            return round(max(0, val), 2), "Simples (Base Única)"
        else:
            if uf_destino in ESTADOS_BASE_DUPLA:
                base_liq = row['Base_Calculo_DIFAL'] - row['V_ICMS_Origem']
                base_cheia = base_liq / (1 - aliq_int)
                val = (base_cheia * aliq_int) - row['V_ICMS_Origem']
                return round(max(0, val), 2), "Normal (Base Dupla)"
            val = row['Base_Calculo_DIFAL'] * (aliq_int - aliq_ori)
            return round(max(0, val), 2), "Normal (Base Única)"
    except: return 0.0, "Erro no cálculo"

def main():
    st.set_page_config(page_title="Dizimeiro - Auditor", layout="wide")
    st.title("💰 O Dizimeiro")
    
    with st.sidebar:
        st.header("📜 Configurações")
        cnpj_input = st.text_input("Seu CNPJ (Destinatário)", key="cnpj_alvo")
        meu_regime = st.selectbox("Seu Regime", ["Regime Normal", "Simples Nacional"])
        minha_uf = st.selectbox("Sua UF", list(ALIQUOTAS_INTERNAS.keys()), index=25)
        cnpj_alvo = limpar_cnpj(cnpj_input)

    up_csv = st.file_uploader("📂 Relatório CSV", type=['csv'])
    up_files = st.file_uploader("📁 XMLs ou ZIPs", type=['xml', 'zip'], accept_multiple_files=True)

    if up_csv and up_files and cnpj_alvo:
        try:
            # Tratamento de encoding
            raw_data = up_csv.read()
            try: content = raw_data.decode('utf-8')
            except: content = raw_data.decode('latin-1')
            
            # Lendo CSV com tratamento de colunas vazias
            df_rel = pd.read_csv(io.StringIO(content), sep=';', skiprows=5, on_bad_lines='skip')
            df_rel.columns = [normalizar_texto(c) for c in df_rel.columns]
            
            # Mapeamento dinâmico
            col_vcontabil = next((c for c in df_rel.columns if "VALOR CONTABIL" in c), None)
            col_nota = next((c for c in df_rel.columns if c == "NOTA"), None)
            col_cfop = next((c for c in df_rel.columns if c == "CFOP"), None)
            col_fornecedor = next((c for c in df_rel.columns if "FORNECEDOR" in c), None)

            if not col_vcontabil or not col_nota or not col_cfop:
                st.error("Colunas essenciais não encontradas no CSV.")
                return

            # Limpeza e Conversão Segura
            df_rel = df_rel[df_rel[col_nota].notna() & (~df_rel[col_fornecedor].str.contains('TOTAL', na=False, case=False))]
            # Aqui está o pulo do gato: conversão com função personalizada que ignora lixo
            df_rel['V_Contabil_Rel'] = df_rel[col_vcontabil].apply(converter_valor_ptbr)
            df_rel['Nota_Rel'] = pd.to_numeric(df_rel[col_nota], errors='coerce')
            df_rel['CFOP_Limpo'] = df_rel[col_cfop].astype(str).str.extract(r'(\d{4})')
            
            # Filtro de linhas com valor zerado (lixo ou cabeçalhos repetidos)
            df_rel = df_rel[df_rel['V_Contabil_Rel'] > 0]
            
            # XMLs
            all_xml_ios = []
            for f in up_files: all_xml_ios.extend(extrair_xmls_recursivo(f))
            
            base_xml = []
            for xml_io in all_xml_ios: base_xml.extend(extrair_dados_xml_agrupados(xml_io))
            
            df_xml = pd.DataFrame(base_xml)
            if not df_xml.empty:
                df_xml['CNPJ_Dest_Limpo'] = df_xml['CNPJ_Dest'].apply(limpar_cnpj)
                df_xml_filtered = df_xml[df_xml['CNPJ_Dest_Limpo'] == cnpj_alvo].copy()

                if not df_xml_filtered.empty:
                    df_final = df_xml_filtered.merge(
                        df_rel[['Nota_Rel', 'CFOP_Limpo', 'V_Contabil_Rel']], 
                        left_on=['Nota', 'CFOP'], 
                        right_on=['Nota_Rel', 'CFOP_Limpo'], 
                        how='inner'
                    )

                    if not df_final.empty:
                        res_list = df_final.apply(lambda r: calcular_dizimo(r, meu_regime, minha_uf), axis=1)
                        df_final['DIFAL_Recolher'] = [x[0] for x in res_list]
                        df_final['Logica'] = [x[1] for x in res_list]

                        st.success(f"Dízimo calculado!")
                        st.dataframe(df_final[['Nota', 'Fornecedor', 'CFOP', 'DIFAL_Recolher', 'Logica']])
                        st.metric("Total a Recolher", f"R$ {df_final['DIFAL_Recolher'].sum():,.2f}")
                        
                        output = io.BytesIO()
                        df_final.to_excel(output, index=False, engine='xlsxwriter')
                        st.download_button("📥 Baixar Auditoria", output.getvalue(), "auditoria_dizimeiro.xlsx")
                    else:
                        st.error("Cruzamento vazio. Verifique se os CFOPs no relatório batem com os XMLs.")
                else:
                    st.error(f"CNPJ {cnpj_alvo} não encontrado nos XMLs.")
            else:
                st.error("Erro ao ler XMLs.")
        except Exception as e:
            st.error(f"Erro no processamento: {e}")

if __name__ == "__main__":
    main()
