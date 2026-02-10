import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import io
import re
import zipfile
import unicodedata

# --- CONFIGURAÇÕES DO PERSONAGEM ---
# Nome: Dizimeiro
# Versão: 6.0 - Auditor Anti-Filiais e Especialista em CST/Origem

ALIQUOTAS_INTERNAS = {
    'AC': 19.0, 'AL': 19.0, 'AM': 20.0, 'AP': 18.0, 'BA': 20.5, 'CE': 20.0, 'DF': 20.0,
    'ES': 17.0, 'GO': 19.0, 'MA': 22.0, 'MG': 18.0, 'MS': 17.0, 'MT': 17.0, 'PA': 19.0,
    'PB': 20.0, 'PE': 20.5, 'PI': 21.0, 'PR': 19.5, 'RJ': 22.0, 'RN': 20.0, 'RO': 19.5,
    'RR': 20.0, 'RS': 17.0, 'SC': 17.0, 'SE': 19.0, 'SP': 18.0, 'TO': 20.0
}

SUL_SUDESTE_ORIGEM = ['SP', 'RJ', 'MG', 'PR', 'RS', 'SC']
ESTADOS_BASE_DUPLA = ['MG', 'PR', 'RS', 'SC', 'SP', 'BA', 'PE', 'GO', 'MS', 'AL', 'SE']

def limpar_cnpj(texto):
    if pd.isna(texto): return ""
    return re.sub(r'\D', '', str(texto)).strip()

def obter_raiz_cnpj(cnpj):
    """Extrai os primeiros 8 dígitos do CNPJ para identificar o grupo econômico."""
    return cnpj[:8]

def normalizar_texto(txt):
    if pd.isna(txt): return ""
    txt = str(txt)
    txt = unicodedata.normalize('NFKD', txt).encode('ASCII', 'ignore').decode('ASCII')
    return txt.upper().strip()

def extrair_xmls_recursivo(uploaded_file):
    xml_contents = []
    def process_zip(file_obj):
        try:
            with zipfile.ZipFile(file_obj) as z:
                for name in z.namelist():
                    if name.startswith('__MACOSX') or '/.' in name: continue 
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

def extrair_dados_xml_detalhado(xml_io, cnpj_alvo):
    try:
        tree = ET.parse(xml_io)
        root = tree.getroot()
        ns = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}
        infNfe = root.find('.//nfe:infNFe', ns)
        if infNfe is None: return []

        ide = root.find('.//nfe:ide', ns)
        nNF = int(ide.find('nfe:nNF', ns).text)
        
        emit = root.find('.//nfe:emit', ns)
        emit_cnpj = limpar_cnpj(emit.find('nfe:CNPJ', ns).text)
        emit_nome = emit.find('nfe:xNome', ns).text
        emit_uf = emit.find('nfe:enderEmit/nfe:UF', ns).text
        
        dest = root.find('.//nfe:dest', ns)
        dest_cnpj = limpar_cnpj(dest.find('nfe:CNPJ', ns).text) if dest is not None and dest.find('nfe:CNPJ', ns) is not None else ""
        
        raiz_alvo = obter_raiz_cnpj(cnpj_alvo)
        raiz_emitente = obter_raiz_cnpj(emit_cnpj)
        
        if dest_cnpj != cnpj_alvo or raiz_emitente == raiz_alvo:
            return []

        lista_itens = []
        for det in root.findall('.//nfe:det', ns):
            prod = det.find('nfe:prod', ns)
            imposto = det.find('nfe:imposto', ns)
            
            cProd = str(prod.find('nfe:cProd', ns).text).strip()
            xProd = str(prod.find('nfe:xProd', ns).text).strip()
            cfop_xml = str(prod.find('nfe:CFOP', ns).text).strip()
            
            vProd = float(prod.find('nfe:vProd', ns).text)
            vIPI = float(imposto.find('.//nfe:vIPI', ns).text) if imposto.find('.//nfe:vIPI', ns) is not None else 0.0
            vFrete = float(prod.find('nfe:vFrete', ns).text) if prod.find('nfe:vFrete', ns) is not None else 0.0
            vOutro = float(prod.find('nfe:vOutro', ns).text) if prod.find('nfe:vOutro', ns) is not None else 0.0
            vSeg = float(prod.find('nfe:vSeg', ns).text) if prod.find('nfe:vSeg', ns) is not None else 0.0
            vDesc = float(prod.find('nfe:vDesc', ns).text) if prod.find('nfe:vDesc', ns) is not None else 0.0
            
            base_calc = round(vProd + vIPI + vFrete + vOutro + vSeg - vDesc, 2)
            
            icms_node = imposto.find('.//nfe:ICMS/*', ns)
            orig = icms_node.find('nfe:orig', ns).text if icms_node is not None and icms_node.find('nfe:orig', ns) is not None else "0"
            vICMSST = float(icms_node.find('nfe:vICMSST', ns).text) if icms_node is not None and icms_node.find('nfe:vICMSST', ns) is not None and icms_node.find('nfe:vICMSST', ns).text else 0.0
            
            lista_itens.append({
                'Nota': nNF, 'Emitente': emit_nome, 'UF_Origem': emit_uf,
                'cProd_XML': cProd, 'xProd_XML': xProd, 'Origem_CST': orig,
                'CFOP_XML': cfop_xml, 'Base_Integral': base_calc, 'V_ST_Nota': vICMSST
            })
        return lista_itens
    except: return []

def calcular_dizimo_final(row, regime, uf_destino, usar_gerencial):
    try:
        if row['V_ST_Nota'] > 0.1: return 0.0, "Isento (ST na Nota)"
        if row['UF_Origem'] == uf_destino: return 0.0, "Isento (Interna)"

        if str(row['Origem_CST']) in ['1', '2', '3', '8']:
            aliq_inter = 0.04
            desc_ori = "Importado (4%)"
        else:
            aliq_inter = 0.07 if row['UF_Origem'] in SUL_SUDESTE_ORIGEM and uf_destino not in SUL_SUDESTE_ORIGEM else 0.12
            desc_ori = f"Nacional ({int(aliq_inter*100)}%)"

        aliq_int = ALIQUOTAS_INTERNAS[uf_destino] / 100
        
        if regime == "Regime Normal":
            cfops_alvo = ['1556', '2556', '1407', '2407', '1551', '2551', '1406', '2406']
            cfop_checar = row['CFOP_Ger'] if usar_gerencial else row['CFOP_XML']
            if str(cfop_checar) not in cfops_alvo: return 0.0, "CFOP não tributável"

            if uf_destino in ESTADOS_BASE_DUPLA:
                v_icms_ori = round(row['Base_Integral'] * aliq_inter, 2)
                base_cheia = (row['Base_Integral'] - v_icms_ori) / (1 - aliq_int)
                valor = (base_cheia * aliq_int) - v_icms_ori
                return round(max(0, valor), 2), f"Base Dupla - {desc_ori}"
            else:
                valor = row['Base_Integral'] * (aliq_int - aliq_inter)
                return round(max(0, valor), 2), f"Base Única - {desc_ori}"
        else:
            valor = row['Base_Integral'] * (aliq_int - aliq_inter)
            return round(max(0, valor), 2), f"Antecipação - {desc_ori}"
    except: return 0.0, "Erro"

def main():
    st.set_page_config(page_title="Dizimeiro 6.0", layout="wide")

    # --- ESTILIZAÇÃO RIHANNA (FOCADA E RIGOROSA) ---
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@800&display=swap');
        
        /* Fundo Radial e Limpeza */
        .stApp {
            background: radial-gradient(circle at top right, #FFDEEF 0%, #F8F9FA 100%) !important;
        }
        header, .stDeployButton {
            display: none !important;
        }

        /* Tipografia Montserrat 800 em TUDO */
        * {
            font-family: 'Montserrat', sans-serif !important;
            font-weight: 800 !important;
        }

        /* Título Rosa Vibrante */
        h1 {
            color: #FF69B4 !important;
            text-align: center !important;
            font-size: 3.5rem !important;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.1);
        }

        /* Campos de Entrada Branco Puro */
        .stTextInput input, .stSelectbox div[data-baseweb="select"], .stSidebar {
            background-color: #FFFFFF !important;
            border-radius: 12px !important;
            border: 1px solid #FFDEEF !important;
        }
        
        /* Forçar Sidebar Branca (Sem cinza) */
        section[data-testid="stSidebar"] {
            background-color: #FFFFFF !important;
        }

        /* Zona de Upload Tracejada */
        [data-testid="stFileUploadDropzone"] {
            background-color: #FFFFFF !important;
            border: 2px dashed #FF69B4 !important;
            border-radius: 12px !important;
        }
        
        /* Botão Browse Files */
        [data-testid="stFileUploadDropzone"] button {
            background-color: #FF69B4 !important;
            color: white !important;
            font-size: 0.8rem !important;
            text-transform: none !important;
            border-radius: 8px !important;
        }
        [data-testid="stFileUploadDropzone"] button::first-letter {
            text-transform: uppercase;
        }

        /* Botões Rosa Neon com Sombra Neon Suave */
        .stButton button, .stDownloadButton button {
            background-color: #FF69B4 !important;
            color: white !important;
            width: 100% !important;
            border: none !important;
            border-radius: 12px !important;
            padding: 1rem !important;
            text-transform: uppercase !important;
            box-shadow: 0 0 15px rgba(255, 105, 180, 0.6) !important;
            transition: all 0.3s ease !important;
        }
        .stButton button:hover, .stDownloadButton button:hover {
            transform: translateY(-3px) !important;
            box-shadow: 0 0 25px rgba(255, 105, 180, 0.9) !important;
        }

        /* Cards de Instrução */
        .rihanna-card {
            background: rgba(255, 255, 255, 0.95);
            border-left: 5px solid #FF69B4;
            padding: 1.5rem;
            border-radius: 12px;
            margin-bottom: 1rem;
            box-shadow: 0 4px 10px rgba(0,0,0,0.05);
        }
        </style>
    """, unsafe_allow_html=True)

    st.markdown("<h1>💰 O DIZIMEIRO</h1>", unsafe_allow_html=True)

    col_inst1, col_inst2 = st.columns(2)
    with col_inst1:
        st.markdown('<div class="rihanna-card">📜 <b>PASSO 1:</b> CONFIGURE SEU CNPJ E REGIME NA BARRA LATERAL PARA FILTRAR NOTAS DE TERCEIROS E CALCULAR A BASE CORRETA.</div>', unsafe_allow_html=True)
    with col_inst2:
        st.markdown('<div class="rihanna-card">📁 <b>PASSO 2:</b> SUBA SEUS ARQUIVOS XML OU ZIP (MATRIOSCA). O SISTEMA IGNORA AUTOMATICAMENTE NOTAS DE SUAS FILIAIS.</div>', unsafe_allow_html=True)

    with st.sidebar:
        st.markdown("<h2 style='color:#FF69B4; text-align:center;'>REINO FISCAL</h2>", unsafe_allow_html=True)
        cnpj_input = st.text_input("Seu CNPJ (Destinatário)")
        meu_regime = st.selectbox("Regime Tributário", ["Simples Nacional", "Regime Normal"])
        minha_uf = st.selectbox("UF de Destino", list(ALIQUOTAS_INTERNAS.keys()), index=25)
        cnpj_alvo = limpar_cnpj(cnpj_input)

    up_ger = st.file_uploader("📂 RELATÓRIO GERENCIAL (OPCIONAL)", type=['csv'])
    up_files = st.file_uploader("📁 XMLS OU ZIPS (MATRIOSCA)", type=['xml', 'zip'], accept_multiple_files=True)

    if up_files and cnpj_alvo:
        try:
            all_xml_itens = []
            extracted = []
            for f in up_files: extracted.extend(extrair_xmls_recursivo(f))
            for x in extracted: all_xml_itens.extend(extrair_dados_xml_detalhado(x, cnpj_alvo))
            
            df_final = pd.DataFrame(all_xml_itens)
            if df_final.empty:
                st.warning("NENHUM XML DE TERCEIROS (EXTERNO AO GRUPO) ENCONTRADO PARA ESTE CNPJ.")
                return

            usar_ger = False
            if up_ger:
                try:
                    df_ger = pd.read_csv(up_ger, sep=';', header=None, encoding='latin-1', on_bad_lines='skip')
                    df_ger = df_ger.rename(columns={0: 'Nota_Ger', 6: 'CFOP_Ger', 7: 'cProd_Ger', 8: 'Desc_Ger'})
                    df_ger['Nota_Ger'] = pd.to_numeric(df_ger['Nota_Ger'], errors='coerce')
                    df_ger['cProd_Ger'] = df_ger['cProd_Ger'].astype(str).str.strip()
                    df_final = df_final.merge(df_ger[['Nota_Ger', 'cProd_Ger', 'CFOP_Ger', 'Desc_Ger']], 
                                            left_on=['Nota', 'cProd_XML'], right_on=['Nota_Ger', 'cProd_Ger'], how='left')
                    usar_ger = True
                except: st.warning("ERRO AO LER GERENCIAL.")

            res = df_final.apply(lambda r: calcular_dizimo_final(r, meu_regime, minha_uf, usar_ger), axis=1)
            df_final['DIFAL_Recolher'] = [x[0] for x in res]
            df_final['Analise'] = [x[1] for x in res]

            st.markdown(f"<h2 style='text-align:center; color:#FF69B4;'>TOTAL A RECOLHER: R$ {df_final['DIFAL_Recolher'].sum():,.2f}</h2>", unsafe_allow_html=True)
            st.dataframe(df_final[df_final['DIFAL_Recolher'] > 0][['Nota', 'Emitente', 'Analise', 'DIFAL_Recolher']])
            
            out = io.BytesIO()
            df_final.to_excel(out, index=False)
            st.download_button("📥 BAIXAR AUDITORIA COMPLETA", out.getvalue(), "Auditoria_Dizimeiro_Rihanna.xlsx")
        except Exception as e: st.error(f"ERRO: {e}")

if __name__ == "__main__":
    main()
