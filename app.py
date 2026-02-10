import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import io
import re
import zipfile
import unicodedata

# --- CONFIGURAÇÕES DO PERSONAGEM ---
# Nome: Dizimeiro
# Versão: 2.0 - Híbrida (XML Puro ou Cruzamento Gerencial)

ALIQUOTAS_INTERNAS = {
    'AC': 19.0, 'AL': 19.0, 'AM': 20.0, 'AP': 18.0, 'BA': 20.5, 'CE': 20.0, 'DF': 20.0,
    'ES': 17.0, 'GO': 19.0, 'MA': 22.0, 'MG': 18.0, 'MS': 17.0, 'MT': 17.0, 'PA': 19.0,
    'PB': 20.0, 'PE': 20.5, 'PI': 21.0, 'PR': 19.5, 'RJ': 22.0, 'RN': 20.0, 'RO': 19.5,
    'RR': 20.0, 'RS': 17.0, 'SC': 17.0, 'SE': 19.0, 'SP': 18.0, 'TO': 20.0
}

ESTADOS_BASE_DUPLA = ['MG', 'PR', 'RS', 'SC', 'SP', 'BA', 'PE', 'GO', 'MS', 'AL', 'SE']

def limpar_cnpj(texto):
    if pd.isna(texto): return ""
    return re.sub(r'\D', '', str(texto)).strip()

def normalizar_texto(txt):
    if pd.isna(txt): return ""
    txt = str(txt)
    txt = unicodedata.normalize('NFKD', txt).encode('ASCII', 'ignore').decode('ASCII')
    return txt.upper().strip()

def converter_valor_seguro(val):
    if pd.isna(val) or val == "": return 0.0
    v = str(val).strip()
    try:
        if ',' in v and '.' in v: v = v.replace('.', '').replace(',', '.')
        elif ',' in v: v = v.replace(',', '.')
        return round(float(v), 4)
    except: return 0.0

def extrair_xmls_recursivo(uploaded_file):
    """Lógica Matriosca: Descompacta ZIPs dentro de ZIPs até encontrar XMLs."""
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

def extrair_dados_xml_detalhado(xml_io):
    """Extrai dados de cada item do XML para auditoria."""
    try:
        tree = ET.parse(xml_io)
        root = tree.getroot()
        ns = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}
        infNfe = root.find('.//nfe:infNFe', ns)
        if infNfe is None: return []

        ide = root.find('.//nfe:ide', ns)
        nNF = int(ide.find('nfe:nNF', ns).text)
        uf_emit = ide.find('nfe:cUF', ns).text # UF de Origem
        
        emit = root.find('.//nfe:emit', ns)
        emit_cnpj = emit.find('nfe:CNPJ', ns).text
        emit_nome = emit.find('nfe:xNome', ns).text
        emit_uf = emit.find('nfe:enderEmit/nfe:UF', ns).text
        
        dest = root.find('.//nfe:dest', ns)
        dest_cnpj = dest.find('nfe:CNPJ', ns).text if dest is not None and dest.find('nfe:CNPJ', ns) is not None else ""
        dest_uf = dest.find('nfe:enderDest/nfe:UF', ns).text if dest is not None and dest.find('nfe:enderDest/nfe:UF', ns) is not None else ""
        
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
            pICMS = float(icms_node.find('nfe:pICMS', ns).text) if icms_node is not None and icms_node.find('nfe:pICMS', ns) is not None and icms_node.find('nfe:pICMS', ns).text else 0.0
            vICMS = float(icms_node.find('nfe:vICMS', ns).text) if icms_node is not None and icms_node.find('nfe:vICMS', ns) is not None and icms_node.find('nfe:vICMS', ns).text else 0.0
            vICMSST = float(icms_node.find('nfe:vICMSST', ns).text) if icms_node is not None and icms_node.find('nfe:vICMSST', ns) is not None and icms_node.find('nfe:vICMSST', ns).text else 0.0
            
            lista_itens.append({
                'Nota': nNF, 
                'Emitente': emit_nome,
                'UF_Origem': emit_uf,
                'CNPJ_Dest_XML': dest_cnpj,
                'cProd_XML': cProd,
                'xProd_XML': xProd,
                'CFOP_Saida': cfop_xml,
                'Base_Calculo': base_calc,
                'V_ICMS_Origem': vICMS,
                'Aliq_Inter': pICMS,
                'V_ST_Nota': vICMSST
            })
        return lista_itens
    except Exception:
        return []

def calcular_dizimo_final(row, regime, uf_destino, usar_gerencial):
    try:
        # 1. Regra de Ouro: Se já teve ST no item, o dízimo já foi pago
        if row['V_ST_Nota'] > 0.1:
            return 0.0, "Isento (ST Destacada)"
        
        # 2. Verificar Fronteira
        if row['UF_Origem'] == uf_destino:
            return 0.0, "Isento (Operação Interna)"

        # 3. Lógica por Regime
        if regime == "Simples Nacional":
            # No Simples, se veio de fora e não tem ST, o Dizimeiro cobra.
            aliq_int = ALIQUOTAS_INTERNAS[uf_destino] / 100
            aliq_ori = row['Aliq_Inter'] / 100
            valor = row['Base_Calculo'] * (aliq_int - aliq_ori)
            return round(max(0, valor), 2), "Dízimo Simples (Antecipação)"
        
        else:
            # Regime Normal: Precisa ser Uso/Consumo ou Ativo (CFOPs específicos)
            cfops_alvo = ['1556', '2556', '1407', '2407', '1551', '2551', '1406', '2406']
            
            # Se não tem gerencial, avisamos que a análise é genérica baseada no XML
            cfop_para_checar = row['CFOP_Entrada'] if usar_gerencial else row['CFOP_Saida']
            
            if usar_gerencial and str(cfop_para_checar) not in cfops_alvo:
                return 0.0, f"CFOP {cfop_para_checar} não tributável"

            aliq_int = ALIQUOTAS_INTERNAS[uf_destino] / 100
            aliq_ori = row['Aliq_Inter'] / 100

            if uf_destino in ESTADOS_BASE_DUPLA:
                base_liq = row['Base_Calculo'] - row['V_ICMS_Origem']
                base_cheia = base_liq / (1 - aliq_int)
                valor = (base_cheia * aliq_int) - row['V_ICMS_Origem']
                return round(max(0, valor), 2), "Dízimo Normal (Base Dupla)"
            else:
                valor = row['Base_Calculo'] * (aliq_int - aliq_ori)
                return round(max(0, valor), 2), "Dízimo Normal (Base Única)"
    except:
        return 0.0, "Erro no cálculo"

def main():
    st.set_page_config(page_title="Dizimeiro - Auditor Fiscal", layout="wide")
    st.title("💰 O Dizimeiro")
    st.markdown("---")

    with st.sidebar:
        st.header("📜 Configurações do Reino")
        cnpj_input = st.text_input("Seu CNPJ (Destinatário)", placeholder="Apenas números")
        meu_regime = st.selectbox("Regime Tributário", ["Simples Nacional", "Regime Normal"])
        minha_uf = st.selectbox("UF de Destino", list(ALIQUOTAS_INTERNAS.keys()), index=25) # SP Default
        cnpj_alvo = limpar_cnpj(cnpj_input)

    col1, col2 = st.columns(2)
    with col1:
        up_gerencial = st.file_uploader("📂 Relatório Gerencial (Opcional)", type=['csv'])
        if not up_gerencial:
            st.info("💡 Modo 'Vigilante': Auditando apenas pelos XMLs (Ideal para Simples Nacional).")
    with col2:
        up_files = st.file_uploader("📁 XMLs ou ZIPs (Matriosca)", type=['xml', 'zip'], accept_multiple_files=True)

    if up_files and cnpj_alvo:
        try:
            # 1. Extração Recursiva de XMLs
            all_xml_itens = []
            extracted_xmls = []
            for f in up_files:
                extracted_xmls.extend(extrair_xmls_recursivo(f))
            
            for xml_io in extracted_xmls:
                all_xml_itens.extend(extrair_dados_xml_detalhado(xml_io))
            
            df_base = pd.DataFrame(all_xml_itens)
            if df_base.empty:
                st.error("Nenhum dado encontrado nos XMLs.")
                return

            df_base['CNPJ_Dest_Limpo'] = df_base['CNPJ_Dest_XML'].apply(limpar_cnpj)
            df_final = df_base[df_base['CNPJ_Dest_Limpo'] == cnpj_alvo].copy()

            if df_final.empty:
                st.error(f"Nenhum XML encontrado para o CNPJ {cnpj_alvo}.")
                return

            # 2. Cruzamento com Gerencial (se existir)
            usar_gerencial = False
            if up_gerencial:
                try:
                    df_ger = pd.read_csv(up_gerencial, sep=';', header=None, encoding='latin-1', on_bad_lines='skip')
                    # Mapeamento: 0:Nota, 6:CFOP, 7:CodProd, 8:Desc
                    df_ger = df_ger.rename(columns={0: 'Nota_Ger', 6: 'CFOP_Ger', 7: 'cProd_Ger', 8: 'Desc_Ger'})
                    df_ger['Nota_Ger'] = pd.to_numeric(df_ger['Nota_Ger'], errors='coerce')
                    df_ger['cProd_Ger'] = df_ger['cProd_Ger'].astype(str).str.strip()
                    
                    df_final = df_final.merge(
                        df_ger[['Nota_Ger', 'cProd_Ger', 'CFOP_Ger', 'Desc_Ger']], 
                        left_on=['Nota', 'cProd_XML'], 
                        right_on=['Nota_Ger', 'cProd_Ger'], 
                        how='left'
                    )
                    df_final['CFOP_Entrada'] = df_final['CFOP_Ger']
                    usar_gerencial = True
                except:
                    st.warning("Falha ao ler Gerencial. Prosseguindo apenas com XMLs.")

            # 3. Cálculo do Tributo
            res = df_final.apply(lambda r: calcular_dizimo_final(r, meu_regime, minha_uf, usar_gerencial), axis=1)
            df_final['DIFAL_Valor'] = [x[0] for x in res]
            df_final['Analise_Fiscal'] = [x[1] for x in res]

            # 4. Exibição dos Resultados
            st.success(f"Auditoria concluída: {len(df_final)} itens processados.")
            
            total_dizimo = df_final['DIFAL_Valor'].sum()
            st.metric("Total de Dízimo (DIFAL/Antecipação)", f"R$ {total_dizimo:,.2f}")

            # Filtro para mostrar apenas o que tem valor ou erros
            df_view = df_final[df_final['DIFAL_Valor'] > 0].copy()
            
            st.write("### 📜 Notas com Tributo Identificado")
            cols = ['Nota', 'Emitente', 'UF_Origem', 'xProd_XML', 'DIFAL_Valor', 'Analise_Fiscal']
            st.dataframe(df_view[cols].sort_values(by='DIFAL_Valor', ascending=False))

            # Exportação
            towrite = io.BytesIO()
            df_final.to_excel(towrite, index=False, engine='xlsxwriter')
            st.download_button("📥 Baixar Livro de Auditoria (Excel)", towrite.getvalue(), "Auditoria_Dizimeiro.xlsx")

        except Exception as e:
            st.error(f"Erro no processamento: {e}")
    elif not cnpj_alvo and up_files:
        st.warning("O Dizimeiro aguarda o CNPJ do destinatário para iniciar a cobrança.")

if __name__ == "__main__":
    main()
