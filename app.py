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

        # 🔥 AMS PRIORIDADE
        if "ont:" in l and ".lt" in l and ".pon" in l:
            return "AMS"

        # 🔥 NCE / IMASTER COM ONUID (ANTES DE PRIMÁRIA)
        if "frame=" in l and "slot=" in l and "port=" in l and "onuid" in l:
            return "IMASTER"

        # 🔥 PRIMÁRIA
        if "los" in l or "fiber is broken" in l:
            return "PRIMARIA"

        if "pon port:" in l and ".lt" in l and ".pon" in l:
            return "PRIMARIA"

        if "location=frame" in l:
            return "PRIMARIA"

        # OUTROS
        if "frame=" in l and "slot=" in l and "port=" in l:
            return "IMASTER"

        if "onuid" in l:
            return "IMASTER"

        if "zte" in l or "com.zte" in l:
            return "ZTE"

        if re.search(r'\bams\b', l):
            return "AMS"

        if "\t" in linha and ("off line" in l or "link loss" in l):
            return "UNM2000"

    return "IMASTER"


# =======================
# AMS (ONT DIRETO)
# =======================

def extrair_onts_ams(linhas):
    resultado = []

    for linha in linhas:
        linha = linha.strip()
        match = re.search(r'ONT:[^,]+', linha)
        if match:
            resultado.append(match.group(0))

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

            olt_match = re.search(r'(olt[^\s,]+)', linha.lower())
            slot_match = re.search(r'slot=(\d+)', linha.lower())
            port_match = re.search(r'port=(\d+)', linha.lower())

            if olt_match and slot_match and port_match:
                olt = olt_match.group(1)
                slot = int(slot_match.group(1))
                port = int(port_match.group(1))

                agrupado[(olt, data)].add((slot, port))

            continue

        # ================= IMASTER / NCE =================
        if gerencia == "IMASTER":

            try:
                olt_match = re.search(r'(olt[^\s,]+)', linha.lower())
                slot_match = re.search(r'slot=(\d+)', linha)
                port_match = re.search(r'port=(\d+)', linha)
                onu_match = re.search(r'onuid=(\d+)', linha.lower())

                # 🔥 CONTRATO (Password OU Description)
                contrato_match = re.search(r'password=(\d+)', linha.lower())
                if not contrato_match:
                    contrato_match = re.search(r'description.*?=(\d+)', linha.lower())

                if not (olt_match and slot_match and port_match):
                    continue

                olt = olt_match.group(1)
                slot = int(slot_match.group(1))
                port = int(port_match.group(1))

                onu = int(onu_match.group(1)) if onu_match else 0
                contrato = contrato_match.group(1) if contrato_match else "NCE"

            except:
                continue

        # ================= UNM2000 =================
        elif gerencia == "UNM2000":
            colunas = linha.split("\t")

            if len(colunas) < 6:
                continue

            try:
                cliente = colunas[1]

                if " " in cliente:
                    contrato = cliente.split(" ")[0]
                elif "_" in cliente:
                    contrato = cliente.split("_")[0]
                else:
                    contrato = cliente

                slot = int(colunas[3])
                port = int(colunas[4])
                onu = int(colunas[5])
                olt = "OLT-UNM"

            except:
                continue

        # ================= ZTE =================
        else:
            colunas = linha.split("\t")

            if len(colunas) < 4:
                continue

            try:
                if not colunas[2].isdigit():
                    continue

                onu = int(colunas[2])
                contrato = colunas[3]

                slot = 1
                port = 1
                olt = "OLT-ZTE"

            except:
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

            # 🔥 ordena por ONU
            lista = sorted(dados, key=lambda x: x["onu"])

            resultado += f"""ALARME GPON – FALHA SECUNDÁRIA

{olt} - {slot}/{port}

ONUs e CONTRATOS AFETADOS:

"""

            for e in lista:
                resultado += f"ONU {e['onu']} - Contrato {e['contrato']}\n"

    return resultado


# =======================
# INTERFACE WEB
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
