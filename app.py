import streamlit as st
from collections import defaultdict
from datetime import datetime
import re


# =======================
# DETECTAR GERÊNCIA
# =======================

def detectar_gerencia(linhas):
    for linha in linhas:
        l = linha.lower()

        # PRIMÁRIA precisa vir antes
        if "pon port:" in l and "los" in l:
            return "PRIMARIA"

        if "los" in l or "feeder fiber is broken" in l:
            if "onuid=" in l:
                return "IMASTER"
            return "PRIMARIA"

        # AMS ONT
        if "ont:" in l and ".lt" in l and ".pon" in l:
            return "AMS"

        # AMS SFP
        if "ethernet lt port:" in l:
            return "AMS_SFP"

        # IMASTER / NCE
        if "frame=" in l and "slot=" in l and "port=" in l:
            return "IMASTER"

        if "onuid" in l:
            return "IMASTER"

        # ZTE
        if "zte" in l or "com.zte" in l:
            return "ZTE"

        # UNM
        if "\t" in linha and ("off line" in l or "link loss" in l):
            return "UNM2000"

    return "IMASTER"


# =======================
# AMS ONT
# =======================

def extrair_onts_ams(linhas):
    resultado = []

    for linha in linhas:
        match = re.search(r'ONT:[^,\s]+', linha)
        if match:
            resultado.append(match.group(0))

    return "\n".join(resultado)


# =======================
# AMS SFP
# =======================

def extrair_sfp_ams(linhas):
    resultado = []

    for linha in linhas:
        match = re.search(r'Ethernet LT Port:([^,]+,SFP)', linha)
        if match:
            resultado.append(match.group(1))

    return "\n".join(resultado)


# =======================
# PROCESSAR LINHAS
# =======================

def processar_linhas(gerencia, linhas, data):

    if gerencia == "PRIMARIA":
        agrupado = defaultdict(set)
    else:
        agrupado = defaultdict(list)

    for linha in linhas:
        linha = linha.strip()

        if not linha:
            continue

        # ================= PRIMÁRIA =================
        if gerencia == "PRIMARIA":
            try:
                olt_match = re.search(r'PON Port:([^,]+)', linha, re.IGNORECASE)
                slot_match = re.search(r'\.LT(\d+)', linha, re.IGNORECASE)
                port_match = re.search(r'\.PON(\d+)', linha, re.IGNORECASE)

                if olt_match and slot_match and port_match:
                    olt = olt_match.group(1)
                    slot = int(slot_match.group(1))
                    port = int(port_match.group(1))

                    agrupado[(olt, data)].add((slot, port))
                    continue

            except:
                continue

        # ================= IMASTER =================
        elif gerencia == "IMASTER":
            try:
                colunas = linha.split("\t")

                if len(colunas) >= 6:
                    # OLT
                    olt = colunas[4] if len(colunas) > 4 else "OLT-NCE"

                olt_match = re.search(r'(olt[^\s\t,]+)', linha, re.IGNORECASE)
                slot_match = re.search(r'Slot=(\d+)', linha, re.IGNORECASE)
                port_match = re.search(r'Port=(\d+)', linha, re.IGNORECASE)
                onu_match = re.search(r'ONUID=(\d+)', linha, re.IGNORECASE)
                contrato_match = re.search(
                    r'Password=(\d+)|Description of the ONT\(only for NMS\)=(\d+)',
                    linha,
                    re.IGNORECASE
                )

                if not (olt_match and slot_match and port_match):
                    continue

                olt = olt_match.group(1)
                slot = int(slot_match.group(1))
                port = int(port_match.group(1))
                onu = int(onu_match.group(1)) if onu_match else 0

                contrato = "NCE"
                if contrato_match:
                    contrato = contrato_match.group(1) or contrato_match.group(2)

            except:
                continue

        # ================= UNM2000 =================
        elif gerencia == "UNM2000":
            colunas = linha.split("\t")

            if len(colunas) < 6:
                continue

            try:
                cliente = colunas[1]

                contrato = cliente.split("_")[0]

                slot = int(colunas[3])
                port = int(colunas[4])
                onu = int(colunas[5])
                olt = "OLT-UNM"

            except:
                continue

        # ================= ZTE =================
        elif gerencia == "ZTE":
            colunas = linha.split("\t")

            if len(colunas) < 4:
                continue

            try:
                onu = int(colunas[2])
                contrato = colunas[3]

                slot = 1
                port = 1
                olt = "OLT-ZTE"

            except:
                continue

        else:
            continue

        chave = (olt, slot, port, data)

        agrupado[chave].append({
            "onu": onu,
            "contrato": contrato
        })

    return agrupado


# =======================
# GERAR TEXTO
# =======================

def gerar_tickets_texto(gerencia, linhas):
    data = datetime.now().strftime("%Y-%m-%d %H:%M")
    agrupado = processar_linhas(gerencia, linhas, data)

    resultado = ""

    for chave, dados in agrupado.items():
        resultado += "\n============================\n"

        if gerencia == "PRIMARIA":
            olt, data = chave
            portas = sorted(dados)

            resultado += f"""ALARME GPON – FALHA PRIMÁRIA

{olt}

PORTAS GPON AFETADAS:

"""

            for slot, port in portas:
                resultado += f"SLOT {slot} / PON {port}\n"

        else:
            olt, slot, port, data = chave
            lista = sorted(dados, key=lambda x: x["onu"])

            resultado += f"""ALARME GPON – FALHA SECUNDÁRIA

{olt} - {slot}/{port}

ONUs e CONTRATOS AFETADOS:

"""

            for e in lista:
                resultado += f"ONU {e['onu']} - Contrato {e['contrato']}\n"

    return resultado


# =======================
# INTERFACE
# =======================

st.set_page_config(page_title="Gerador GPON", layout="wide")
st.title("🔧 Gerador de Alarmes GPON")

entrada = st.text_area("Cole os alarmes aqui:", height=300)

col1, col2 = st.columns(2)

with col1:
    if st.button("🚀 Gerar Alarme"):
        if entrada.strip():
            linhas = entrada.strip().split("\n")
            gerencia = detectar_gerencia(linhas)

            if gerencia == "AMS":
                resultado = extrair_onts_ams(linhas)

            elif gerencia == "AMS_SFP":
                resultado = extrair_sfp_ams(linhas)

            else:
                resultado = gerar_tickets_texto(gerencia, linhas)

            st.session_state["resultado"] = resultado
        else:
            st.warning("Cole algum conteúdo primeiro.")

with col2:
    if st.button("🧹 Limpar"):
        st.session_state["resultado"] = ""
        st.rerun()

if "resultado" in st.session_state:
    st.text_area("Resultado:", st.session_state["resultado"], height=300)
