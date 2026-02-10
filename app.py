import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import io
import re
import zipfile
import unicodedata

# --- CONFIGURAÇÃO E ESTILO (DESIGN RIHANNA ORIGINAL - UNIFICADO E TRAVADO) ---
st.set_page_config(page_title="DIZIMEIRO", layout="wide", page_icon="💰")

def aplicar_estilo_rihanna_original():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;800&family=Plus+Jakarta+Sans:wght@400;700&display=swap');

        /* Limpeza de Header e Sidebar */
        header, [data-testid="stHeader"], .stDeployButton { display: none !important; }
        [data-testid="sidebar-close"], [data-testid="collapsedControl"] { display: none !important; }
        
        .stApp { 
            background: radial-gradient(circle at top right, #FFDEEF 0%, #F8F9FA 100%) !important; 
        }

        [data-testid="stSidebar"] {
            background-color: #FFFFFF !important;
            border-right: 1px solid #FFDEEF !important;
            min-width: 400px !important;
            max-width: 400px !important;
        }

        /* Tipografia Montserrat */
        * {
            font-family: 'Montserrat', sans-serif !important;
            font-weight: 400;
        }

        /* Títulos */
        h1, h2, h3 {
            font-weight: 800 !important;
            color: #FF69B4 !important;
            text-align: center;
        }

        /* Botões Estilo Mercador (Brancos com Hover Rosa) */
        div.stButton > button {
            color: #6C757D !important; 
            background-color: #FFFFFF !important; 
            border: 1px solid #DEE2E6 !important;
            border-radius: 15px !important;
            font-weight: 800 !important;
            height: 60px !important;
            text-transform: uppercase;
            transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275) !important;
        }

        div.stButton > button:hover {
            transform: translateY(-5px) !important;
            box-shadow: 0 10px 20px rgba(255,105,180,0.2) !important;
            border-color: #FF69B4 !important;
            color: #FF69B4 !important;
        }

        /* Uploader Tracejado Rosa */
        [data-testid="stFileUploader"] { 
            border: 2px dashed #FF69B4 !important; 
            border-radius: 20px !important;
            background: #FFFFFF !important;
            padding: 20px !important;
        }

        /* Botão de Download Rosa Neon */
        div.stDownloadButton > button {
            background-color: #FF69B4 !important; 
            color: white !important; 
            border: 2px solid #FFFFFF !important;
            font-weight: 800 !important;
            border-radius: 15px !important;
            box-shadow: 0 0 15px rgba(255, 105, 180, 0.6) !important;
            text-transform: uppercase;
            width: 100% !important;
            transition: all 0.4s ease !important;
        }
        
        div.stDownloadButton > button:hover {
            transform: translateY(-5px) !important;
            box-shadow: 0 0 30px rgba(255, 105, 180, 1) !important;
        }

        /* Inputs e Cards */
        .stTextInput>div>div>input {
            border: 2px solid #FFDEEF !important;
            border-radius: 10px !important;
            padding: 10px !important;
        }

        .instrucoes-card {
            background-color: rgba(255, 255, 255, 0.7);
            border-radius: 15px;
            padding: 20px;
            border-left: 5px solid #FF69B4;
            margin-bottom: 20px;
            min-height: 180px;
        }
        </style>
    """, unsafe_allow_html=True)

# --- LÓGICA DE NEGÓCIO DIZIMEIRO 6.0 ---
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

def buscar_tag(tag, no):
    """Busca tag ignorando namespace"""
    for elemento in no.iter():
        if elemento.tag.split('}')[-1] == tag:
            return elemento
    return None

def extrair_dados_xml_detalhado(xml_io, cnpj_alvo):
    try:
        # Limpeza agressiva de namespaces para não falhar na leitura
        xml_str = xml_io.read().decode('utf-8', errors='ignore')
        xml_str = re.sub(r'\sxmlns(:\w+)?="[^"]+"', '', xml_str)
        root = ET.fromstring(xml_str)
        
        ide = buscar_tag('ide', root)
        nNF = int(buscar_tag('nNF', ide).text)
        
        emit = buscar_tag('emit', root)
        emit_cnpj = limpar_cnpj(buscar_tag('CNPJ', emit).text)
        
        dest = buscar_tag('dest', root)
        dest_cnpj = limpar_cnpj(buscar_tag('CNPJ', dest).text)
        
        # Auditoria de Terceiros e Filiais
        if dest_cnpj != cnpj_alvo or obter_raiz_cnpj(emit_cnpj) == obter_raiz_cnpj(cnpj_alvo):
            return []

        itens = []
        for det in root.findall('.//det'):
            prod = buscar_tag('prod', det)
            imp = buscar_tag('imposto', det)
            vProd = float(buscar_tag('vProd', prod).text)
            vIPI = float(buscar_tag('vIPI', imp).text) if buscar_tag('vIPI', imp) is not None else 0.0
            icms = buscar_tag('ICMS', imp)
            
            # Pega o primeiro nó dentro de ICMS (ICMS00, ICMS40, etc)
            icms_detalhe = list(icms)[0] if icms is not None else None
            
            itens.append({
                'Nota': nNF, 
                'Emitente': buscar_tag('xNome', emit).text, 
                'UF_Origem': buscar_tag('UF', emit).text,
                'cProd_XML': str(buscar_tag('cProd', prod).text).strip(),
                'CFOP_XML': str(buscar_tag('CFOP', prod).text).strip(),
                'Base_Integral': round(vProd + vIPI, 2),
                'Origem_CST': buscar_tag('orig', icms_detalhe).text if buscar_tag('orig', icms_detalhe) is not None else "0",
                'V_ST_Nota': float(buscar_tag('vICMSST', icms_detalhe).text) if buscar_tag('vICMSST', icms_detalhe) is not None else 0.0
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

def main():
    aplicar_estilo_rihanna_original()
    st.markdown("<h1>💰 O DIZIMEIRO</h1>", unsafe_allow_html=True)

    with st.container():
        col1, col2 = st.columns(2)
        with col1:
            st.markdown('<div class="instrucoes-card"><h3>📖 Regras</h3><p>• Informe o CNPJ para validar as notas de terceiros.<br>• Notas do mesmo grupo econômico (filiais) são ignoradas.</p></div>', unsafe_allow_html=True)
        with col2:
            st.markdown('<div class="instrucoes-card"><h3>📊 Auditoria</h3><p>• Cálculo automático de DIFAL e Antecipação.<br>• Identificação de origem (CST) e IPI na base.</p></div>', unsafe_allow_html=True)

    with st.sidebar:
        st.markdown("### 🔍 Configuração")
        cnpj_input = st.text_input("CNPJ DO CLIENTE", placeholder="00.000.000/0001-00")
        regime_input = st.selectbox("REGIME FISCAL", ["Simples Nacional", "Regime Normal"])
        uf_input = st.selectbox("UF DE DESTINO", list(ALIQUOTAS_INTERNAS.keys()), index=25)
        cnpj_limpo = limpar_cnpj(cnpj_input)

    if cnpj_limpo and len(cnpj_limpo) == 14:
        up_ger = st.file_uploader("1. Relatório GERENCIAL (CSV/Opcional)", type=['csv'])
        up_xml = st.file_uploader("2. XMLs ou ZIPs aqui:", accept_multiple_files=True)

        if up_xml:
            if st.button("🚀 INICIAR APURAÇÃO DIAMANTE"):
                all_itens = []
                for f in up_xml:
                    for x_io in extrair_xmls_recursivo(f):
                        all_itens.extend(extrair_dados_xml_detalhado(x_io, cnpj_limpo))
                
                if all_itens:
                    df_final = pd.DataFrame(all_itens)
                    usar_g = False
                    if up_ger:
                        try:
                            dg = pd.read_csv(up_ger, sep=';', header=None, encoding='latin-1')
                            dg = dg.rename(columns={0:'Nota_Ger', 6:'CFOP_Ger', 7:'cProd_Ger'})
                            df_final = df_final.merge(dg[['Nota_Ger', 'cProd_Ger', 'CFOP_Ger']], left_on=['Nota', 'cProd_XML'], right_on=['Nota_Ger', 'cProd_Ger'], how='left')
                            usar_g = True
                        except: st.error("Erro no Gerencial.")
                    
                    res = df_final.apply(lambda r: calcular_dizimo_final(r, regime_input, uf_input, usar_g), axis=1)
                    df_final['DIFAL_Recolher'] = [x[0] for x in res]
                    df_final['Analise'] = [x[1] for x in res]
                    
                    st.markdown(f"<h2>TOTAL A RECOLHER: R$ {df_final['DIFAL_Recolher'].sum():,.2f}</h2>", unsafe_allow_html=True)
                    st.dataframe(df_final[df_final['DIFAL_Recolher'] > 0][['Nota', 'Emitente', 'Analise', 'DIFAL_Recolher']])
                    
                    out = io.BytesIO()
                    df_final.to_excel(out, index=False)
                    st.download_button("📥 BAIXAR RELATÓRIO DIAMANTE", out.getvalue(), "Auditoria_Dizimeiro.xlsx")
                else:
                    st.warning("Nenhum XML de terceiros válido foi encontrado para o CNPJ informado.")
    else:
        st.warning("👈 Insira o CNPJ de 14 dígitos na barra lateral para começar.")

if __name__ == "__main__":
    main()
