import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import io
import re
import zipfile
import unicodedata

# --- CONFIGURAÇÕES DO PERSONAGEM ---
# Nome: Dizimeiro (Módulo Gerencial Avançado)
# Função: Auditor de DIFAL de Entrada com cruzamento por Item/Produto.

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
    return re.sub(r'\D', '', str(texto)).strip()

def normalizar_string(txt):
    if pd.isna(txt): return ""
    return str(txt).strip().upper()

def extrair_xmls_recursivo(uploaded_file):
    """Lógica Matriosca: Abre ZIPs dentro de ZIPs recursivamente."""
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

def extrair_dados_xml_itens(xml_io):
    """Extrai dados detalhados de cada item (<det>) do XML."""
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
        dest_cnpj = dest.find('nfe:CNPJ', ns).text if dest is not None and dest.find('nfe:CNPJ', ns) is not None else ""
        
        itens_nfe = []
        for det in root.findall('.//nfe:det', ns):
            prod = det.find('nfe:prod', ns)
            imposto = det.find('nfe:imposto', ns)
            
            cProd = str(prod.find('nfe:cProd', ns).text).strip()
            xProd = str(prod.find('nfe:xProd', ns).text).strip()
            cfop = str(prod.find('nfe:CFOP', ns).text).strip()
            
            vProd = float(prod.find('nfe:vProd', ns).text)
            vIPI = float(imposto.find('.//nfe:vIPI', ns).text) if imposto.find('.//nfe:vIPI', ns) is not None else 0.0
            vFrete = float(prod.find('nfe:vFrete', ns).text) if prod.find('nfe:vFrete', ns) is not None else 0.0
            vOutro = float(prod.find('nfe:vOutro', ns).text) if prod.find('nfe:vOutro', ns) is not None else 0.0
            vSeg = float(prod.find('nfe:vSeg', ns).text) if prod.find('nfe:vSeg', ns) is not None else 0.0
            vDesc = float(prod.find('nfe:vDesc', ns).text) if prod.find('nfe:vDesc', ns) is not None else 0.0
            
            # Base do DIFAL: Soma dos valores que compõem a operação de entrada
            base_calculo = (vProd + vIPI + vFrete + vOutro + vSeg - vDesc)
            
            icms_node = imposto.find('.//nfe:ICMS/*', ns)
            pICMS = float(icms_node.find('nfe:pICMS', ns).text) if icms_node is not None and icms_node.find('nfe:pICMS', ns) is not None and icms_node.find('nfe:pICMS', ns).text else 0.0
            vICMS = float(icms_node.find('nfe:vICMS', ns).text) if icms_node is not None and icms_node.find('nfe:vICMS', ns) is not None and icms_node.find('nfe:vICMS', ns).text else 0.0
            vICMSST = float(icms_node.find('nfe:vICMSST', ns).text) if icms_node is not None and icms_node.find('nfe:vICMSST', ns) is not None and icms_node.find('nfe:vICMSST', ns).text else 0.0
            
            itens_nfe.append({
                'Nota_XML': nNF, 
                'Fornecedor_XML': emit_nome,
                'CNPJ_Dest_XML': dest_cnpj,
                'cProd_XML': cProd,
                'xProd_XML': xProd,
                'CFOP_XML': cfop,
                'Base_Calculo_DIFAL': base_calculo,
                'V_ICMS_Origem': vICMS,
                'Aliq_Inter': pICMS,
                'V_ST_Nota': vICMSST
            })
            
        return itens_nfe
    except:
        return []

def calcular_dizimo_final(row, regime, uf_destino):
    try:
        if row['V_ST_Nota'] > 0.1: return 0.0, "Substituição Tributária Identificada"
        
        # Filtro de CFOPs sujeitos a DIFAL de entrada (Uso/Consumo/Ativo)
        cfops_alvo = ['1556', '2556', '1407', '2407', '1551', '2551', '1406', '2406']
        if str(row['CFOP_Ger']).strip() not in cfops_alvo: 
            return 0.0, f"CFOP {row['CFOP_Ger']} não sujeito"

        aliq_int = ALIQUOTAS_INTERNAS[uf_destino] / 100
        aliq_ori = row['Aliq_Inter'] / 100

        if regime == "Simples Nacional":
            valor = row['Base_Calculo_DIFAL'] * (aliq_int - aliq_ori)
            return round(max(0, valor), 2), "Simples Nacional (Base Única)"
        else:
            if uf_destino in ESTADOS_BASE_DUPLA:
                base_liquida = row['Base_Calculo_DIFAL'] - row['V_ICMS_Origem']
                base_cheia = base_liquida / (1 - aliq_int)
                valor = (base_cheia * aliq_int) - row['V_ICMS_Origem']
                return round(max(0, valor), 2), "Regime Normal (Base Dupla)"
            else:
                valor = row['Base_Calculo_DIFAL'] * (aliq_int - aliq_ori)
                return round(max(0, valor), 2), "Regime Normal (Base Única)"
    except:
        return 0.0, "Erro no cálculo"

def main():
    st.set_page_config(page_title="O Dizimeiro - Auditor Gerencial", layout="wide")
    st.title("💰 O Dizimeiro")
    st.subheader("Auditoria de DIFAL: Cruzamento Gerencial vs XML")

    with st.sidebar:
        st.header("📜 Configurações")
        meu_cnpj_input = st.text_input("Seu CNPJ (Destinatário)")
        meu_regime = st.selectbox("Seu Regime Tributário", ["Regime Normal", "Simples Nacional"])
        minha_uf = st.selectbox("Sua UF de Destino", list(ALIQUOTAS_INTERNAS.keys()), index=25)
        cnpj_alvo = limpar_cnpj(meu_cnpj_input)

    up_gerencial = st.file_uploader("📂 Relatório Gerencial (CSV)", type=['csv'])
    up_files = st.file_uploader("📁 XMLs ou ZIPs (Matriosca)", type=['xml', 'zip'], accept_multiple_files=True)

    if up_gerencial and up_files and cnpj_alvo:
        try:
            # 1. Leitura do Relatório Gerencial (Sem cabeçalho, separado por ;)
            df_ger = pd.read_csv(up_gerencial, sep=';', header=None, encoding='latin-1', on_bad_lines='skip')
            
            # Mapeamento conforme instruções do usuário:
            # Col 1 (Index 0): Nota | Col 7 (Index 6): CFOP | Col 8 (Index 7): Cod Produto | Col 9 (Index 8): Descrição
            df_ger = df_ger.rename(columns={
                0: 'Nota_Ger',
                6: 'CFOP_Ger',
                7: 'cProd_Ger',
                8: 'Desc_Ger'
            })
            
            df_ger['Nota_Ger'] = pd.to_numeric(df_ger['Nota_Ger'], errors='coerce')
            df_ger['cProd_Ger'] = df_ger['cProd_Ger'].astype(str).str.strip()
            df_ger['CFOP_Ger'] = df_ger['CFOP_Ger'].astype(str).str.strip()
            df_ger['Desc_Ger'] = df_ger['Desc_Ger'].apply(normalizar_string)

            # 2. Processamento recursivo de XMLs
            all_xml_itens = []
            progress_bar = st.progress(0)
            
            extracted_xmls = []
            for f in up_files:
                extracted_xmls.extend(extrair_xmls_recursivo(f))
            
            for i, xml_io in enumerate(extracted_xmls):
                all_xml_itens.extend(extrair_dados_xml_itens(xml_io))
                progress_bar.progress((i + 1) / len(extracted_xmls))
            
            df_xml = pd.DataFrame(all_xml_itens)
            
            if not df_xml.empty:
                df_xml['CNPJ_Dest_Limpo'] = df_xml['CNPJ_Dest_XML'].apply(limpar_cnpj)
                df_xml_filtered = df_xml[df_xml['CNPJ_Dest_Limpo'] == cnpj_alvo].copy()

                if not df_xml_filtered.empty:
                    # 3. Cruzamento Triplo: Nota + Código do Produto
                    # Validamos Nota e Código do Produto para garantir que o item é o mesmo.
                    df_final = df_xml_filtered.merge(
                        df_ger[['Nota_Ger', 'cProd_Ger', 'CFOP_Ger', 'Desc_Ger']], 
                        left_on=['Nota_XML', 'cProd_XML'], 
                        right_on=['Nota_Ger', 'cProd_Ger'], 
                        how='inner'
                    )

                    if not df_final.empty:
                        # 4. Cálculo do Dízimo
                        res_list = df_final.apply(lambda r: calcular_dizimo_final(r, meu_regime, minha_uf), axis=1)
                        df_final['DIFAL_Recolher'] = [x[0] for x in res_list]
                        df_final['Status_Fiscal'] = [x[1] for x in res_list]

                        st.success(f"Dízimo auditado em {len(df_final)} itens de mercadoria!")
                        
                        # Exibição com validação de descrição
                        st.write("### 📜 Livro de Registros do Dizimeiro")
                        cols_view = ['Nota_XML', 'Fornecedor_XML', 'cProd_XML', 'Desc_Ger', 'CFOP_Ger', 'DIFAL_Recolher', 'Status_Fiscal']
                        st.dataframe(df_final[cols_view].sort_values(by='DIFAL_Recolher', ascending=False))
                        
                        st.metric("Total de DIFAL a Recolher", f"R$ {df_final['DIFAL_Recolher'].sum():,.2f}")

                        # Exportação
                        towrite = io.BytesIO()
                        df_final.to_excel(towrite, index=False, engine='xlsxwriter')
                        st.download_button("📥 Baixar Auditoria Gerencial Excel", towrite.getvalue(), "Auditoria_Dizimeiro_Gerencial.xlsx")
                    else:
                        st.warning("Cruzamento vazio. Verifique se as Notas e Códigos de Produto no Relatório Gerencial coincidem com os XMLs.")
                        st.write("Amostra Gerencial:", df_ger[['Nota_Ger', 'cProd_Ger']].head())
                        st.write("Amostra XML:", df_xml_filtered[['Nota_XML', 'cProd_XML']].head())
                else:
                    st.error(f"Nenhum XML com o CNPJ {cnpj_alvo} foi encontrado.")
            else:
                st.error("Não foi possível extrair dados dos XMLs.")
        except Exception as e:
            st.error(f"Erro no processamento do Reino: {e}")

if __name__ == "__main__":
    main()
