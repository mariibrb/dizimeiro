import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import io
import re
import zipfile
import unicodedata

# --- CONFIGURAÇÃO E ESTILO (DESIGN RIHANNA 7.0 - SEM LIXO VISUAL) ---
st.set_page_config(page_title="DIZIMEIRO", layout="wide", page_icon="💰")

def aplicar_estilo_rihanna_definitivo():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;700&display=swap');

        /* Omitir Header, Deploy e Setas da Sidebar (Keyboard Double) */
        header, [data-testid="stHeader"], .stDeployButton, [data-testid="sidebar-close"], [data-testid="collapsedControl"] { 
            display: none !important; 
        }
        
        /* Travando a Sidebar para não aparecer botões de colapso */
        section[data-testid="stSidebar"] > div { padding-top: 2rem; }

        /* Fundo Degradê Radial Rihanna */
        .stApp { 
            background: radial-gradient(circle at top right, #FFDEEF 0%, #F8F9FA 100%) !important; 
        }

        /* Sidebar Branco Puro */
        [data-testid="stSidebar"] {
            background-color: #FFFFFF !important;
            border-right: 1px solid #FFDEEF !important;
        }

        /* Tipografia Montserrat (Peso 400 - Sem negrito global) */
        * {
            font-family: 'Montserrat', sans-serif !important;
            font-weight: 400; 
        }

        /* Títulos Rosa Vibrante (Peso 700 apenas aqui) */
        h1, h2, h3 {
            color: #FF69B4 !important;
            text-align: center !important;
            font-weight: 700 !important;
        }

        /* Inputs e Selects Branco Puro */
        .stTextInput>div>div>input, .stSelectbox div[data-baseweb="select"] {
            background-color: #FFFFFF !important;
            border: 1px solid #FFDEEF !important;
            border-radius: 12px !important;
            color: #6C757D !important;
        }

        /* Uploader: Borda Tracejada Rosa */
        [data-testid="stFileUploader"] { 
            border: 2px dashed #FF69B4 !important; 
            border-radius: 20px !important;
            background: #FFFFFF !important;
            padding: 20px !important;
        }

        /* Botão Browse Files com Efeito Neon */
        [data-testid="stFileUploader"] button {
            background-color: #FF69B4 !important;
            color: white !important;
            border-radius: 10px !important;
            border: none !important;
            padding: 8px 20px !important;
            box-shadow: 0 0 10px rgba(255, 105, 180, 0.5) !important;
            transition: all 0.3s ease !important;
        }
        [data-testid="stFileUploader"] button:hover {
            box-shadow: 0 0 20px rgba(255, 105, 180, 1) !important;
            transform: scale(1.05);
        }

        /* Botões de Ação Rosa com Sombra Neon Intensa */
        div.stButton > button, div.stDownloadButton > button {
            background-color: #FF69B4 !important; 
            color: white !important; 
            font-weight: 700 !important;
            border-radius: 15px !important;
            border: none !important;
            height: 60px !important;
            width: 100% !important;
            text-transform: uppercase;
            box-shadow: 0 0 15px rgba(255, 105, 180, 0.4) !important;
            transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275) !important;
        }

        div.stButton > button:hover, div.stDownloadButton > button:hover {
            transform: translateY(-5px) !important;
            box-shadow: 0 10px 30px rgba(255, 105, 180, 0.7) !important;
        }

        /* Cards Rihanna */
        .rihanna-card {
            background-color: rgba(255, 255, 255, 0.85);
            border-radius: 15px;
            padding: 20px;
            border-left: 5px solid #FF69B4;
            margin-bottom: 20px;
        }
        </style>
    """, unsafe_allow_html=True)

# --- LOGICA FISCAL DIZIMEIRO 6.0 ---
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
    return cnpj[:8]

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
        ide = root.find('.//nfe:ide', ns)
        nNF = int(ide.find('nfe:nNF', ns).text)
        emit = root.find('.//nfe:emit', ns)
        emit_cnpj = limpar_cnpj(emit.find('nfe:CNPJ', ns).text)
        dest = root.find('.//nfe:dest', ns)
        dest_cnpj = limpar_cnpj(dest.find('nfe:CNPJ', ns).text)
        if dest_cnpj != cnpj_alvo or obter_raiz_cnpj(emit_cnpj) == obter_raiz_cnpj(cnpj_alvo):
            return []
        itens = []
        for det in root.findall('.//nfe:det', ns):
            prod = det.find('nfe:prod', ns)
            imp = det.find('nfe:imposto', ns)
            vProd = float(prod.find('nfe:vProd', ns).text)
            vIPI = float(imp.find('.//nfe:vIPI', ns).text) if imp.find('.//nfe:vIPI', ns) is not None else 0.0
            icms = imp.find('.//nfe:ICMS/*')
            itens.append({
                'Nota': nNF, 'Emitente': emit.find('nfe:xNome', ns).text, 
                'UF_Origem': emit.find('nfe:enderEmit/nfe:UF', ns).text,
                'cProd_XML': str(prod.find('nfe:cProd', ns).text).strip(),
                'CFOP_XML': str(prod.find('nfe:CFOP', ns).text).strip(),
                'Base_Integral': round(vProd + vIPI, 2),
                'Origem_CST': icms.find('nfe:orig', ns).text if icms is not None else "0",
                'V_ST_Nota': float(icms.find('nfe:vICMSST', ns).text) if icms is not None and icms.find('nfe:vICMSST', ns) is not None else 0.0
            })
        return itens
    except: return []

def calcular_dizimo_final(row, regime, uf_destino, usar_gerencial):
    try:
        if row['V_ST_Nota'] > 0.1: return 0.0, "Isento (ST na Nota)"
        if row['UF_Origem'] == uf_destino: return 0.0, "Isento (Interna)"
        aliq_inter = 0.04 if str(row['Origem_CST']) in ['1', '2', '3', '8'] else (0.07 if row['UF_Origem'] in SUL_SUDESTE_ORIGEM and uf_destino not in SUL_SUDESTE_ORIGEM else 0.12)
        aliq_int = ALIQUOTAS_INTERNAS[uf_destino] / 100
        if regime == "Regime Normal":
            cfops = ['1556', '2556', '1407', '2407', '1551', '2551', '1406', '2406']
            cfop_check = row['CFOP_Ger'] if usar_gerencial else row['CFOP_XML']
            if str(cfop_check) not in cfops: return 0.0, "CFOP não tributável"
            if uf_destino in ESTADOS_BASE_DUPLA:
                v_ori = round(row['Base_Integral'] * aliq_inter, 2)
                base_ch = (row['Base_Integral'] - v_ori) / (1 - aliq_int)
                val = (base_ch * aliq_int) - v_ori
                return round(max(0, val), 2), "Base Dupla"
            return round(max(0, row['Base_Integral'] * (aliq_int - aliq_inter)), 2), "Base Única"
        return round(max(0, row['Base_Integral'] * (aliq_int - aliq_inter)), 2), "Antecipação"
    except: return 0.0, "Erro"

# --- INTERFACE ---
aplicar_estilo_rihanna_definitivo()
st.markdown("<h1>💰 O DIZIMEIRO</h1>", unsafe_allow_html=True)

col_x, col_y = st.columns(2)
with col_x: st.markdown('<div class="rihanna-card">📜 CONFIGURE O CNPJ NA SIDEBAR PARA AUDITAR AS NOTAS DE FORNECEDORES EXTERNOS.</div>', unsafe_allow_html=True)
with col_y: st.markdown('<div class="rihanna-card">📁 ARRASTE XMLS OU ZIPS. O SISTEMA IDENTIFICA O GRUPO E FILTRA FILIAIS AUTOMATICAMENTE.</div>', unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### 🔍 CONFIGURAÇÃO")
    cnpj_in = st.text_input("CNPJ DESTINATÁRIO", placeholder="12.345.678/0001-90")
    regime = st.selectbox("REGIME FISCAL", ["Simples Nacional", "Regime Normal"])
    uf_des = st.selectbox("UF DE DESTINO", list(ALIQUOTAS_INTERNAS.keys()), index=25)
    cnpj_alvo = limpar_cnpj(cnpj_in)

if cnpj_alvo:
    up_ger = st.file_uploader("1. RELATÓRIO GERENCIAL (CSV/OPCIONAL)", type=['csv'])
    up_xml = st.file_uploader("2. XMLS OU ZIPS (MATRIOSCA)", type=['xml', 'zip'], accept_multiple_files=True)

    if up_xml and st.button("🚀 INICIAR AUDITORIA DIAMANTE"):
        all_itens = []
        for f in up_xml:
            for x_io in extrair_xmls_recursivo(f):
                all_itens.extend(extrair_dados_xml_detalhado(x_io, cnpj_alvo))
        
        df = pd.DataFrame(all_itens)
        if not df.empty:
            usar_g = False
            if up_ger:
                try:
                    dg = pd.read_csv(up_ger, sep=';', header=None, encoding='latin-1')
                    dg = dg.rename(columns={0:'Nota_Ger', 6:'CFOP_Ger', 7:'cProd_Ger'})
                    df = df.merge(dg[['Nota_Ger', 'cProd_Ger', 'CFOP_Ger']], left_on=['Nota', 'cProd_XML'], right_on=['Nota_Ger', 'cProd_Ger'], how='left')
                    usar_g = True
                except: st.error("Erro ao ler Gerencial.")
            
            res = df.apply(lambda r: calcular_dizimo_final(r, regime, uf_des, usar_g), axis=1)
            df['DIFAL_Recolher'] = [x[0] for x in res]
            df['Analise'] = [x[1] for x in res]
            
            st.markdown(f"<h2>TOTAL A RECOLHER: R$ {df['DIFAL_Recolher'].sum():,.2f}</h2>", unsafe_allow_html=True)
            st.dataframe(df[df['DIFAL_Recolher'] > 0][['Nota', 'Emitente', 'Analise', 'DIFAL_Recolher']])
            
            out = io.BytesIO()
            df.to_excel(out, index=False)
            st.download_button("📥 BAIXAR RELATÓRIO NEON", out.getvalue(), "Auditoria_Dizimeiro.xlsx")
else:
    st.warning("👈 Insira o CNPJ na lateral para começar.")
