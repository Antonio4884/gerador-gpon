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

        if "ethernet lt port" in l:
            return "SFP"

        if "ont:" in l and ".lt" in l and ".pon" in l:
            return "AMS"

        if "pon port:" in l:
            return "PRIMARIA_PON"

        if "frame=" in l and "slot=" in l and "port=" in l:
            return "IMASTER"

        if "\t" in linha and ("link loss" in l or "off line" in l):
            return "UNM2000"

    return "IMASTER"


# =======================
# EXTRAIR DATA
# =======================

def extrair_data(linhas):
    for linha in linhas:
        match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', linha)
        if match:
            dt = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
            return dt.strftime("%d/%m/%Y %H:%M")

    return datetime.now().strftime("%d/%m/%Y %H:%M")


# =======================
# AMS5520
# =======================

def extrair_onts_ams(linhas):
    onts_completas = []
    portas_sem_ont = []
    olts = set()

    for linha in linhas:
        linha = linha.strip()

        match_full = re.search(
            r'ONT:(OLT\w+:R\d+\.S\d+\.LT\d+\.PON\d+\.ONT\d+)',
            linha,
            re.IGNORECASE
        )

        match_porta = re.search(
            r'ONT:(OLT\w+:R\d+\.S\d+\.LT\d+\.PON\d+)',
            linha,
            re.IGNORECASE
        )

        if match_full:
            onts_completas.append(match_full.group(1).upper())

        if match_porta:
            porta = match_porta.group(1).upper()
            portas_sem_ont.append(porta)

            olt_match = re.search(r'^(OLT[^:]+)', porta)
            if olt_match:
                olts.add(olt_match.group(1))

    portas_unicas = set(portas_sem_ont)

    # se existem várias ONTs na mesma PON = primária
    eh_primaria = len(onts_completas) > len(portas_unicas)

    # ================= PRIMÁRIA =================
    if eh_primaria:
        resultado = "Indisponibilidade em rede PRIMARIA:\n"

        if olts:
            resultado += f"GPON PRIMARIA: {', '.join(sorted(olts))}\n\n"

        for porta in sorted(portas_unicas):
            resultado += f"{porta} - \n"

        return resultado

    # ================= SECUNDÁRIA =================
    resultado = "Indisponibilidade em rede SECUNDARIA:\n"
    resultado += "GPON SECUNDARIA:\n"

    for ont in sorted(set(onts_completas)):
        resultado += f"{ont}\n"

    resultado += "\nHTT-AFETADOS:"
    return resultado


# =======================
# PRIMÁRIA PON PORT
# =======================

def extrair_primaria_pon(linhas):
    resultado = []

    for linha in linhas:
        match = re.search(r'PON Port:([^,]+)', linha)
        if match:
            resultado.append(match.group(1))

    return "\n".join(resultado)


# =======================
# SFP
# =======================

def extrair_sfp(linhas):
    resultado = []

    for linha in linhas:
        match = re.search(r'Ethernet LT Port:([^,]+)', linha)
        if match:
            resultado.append(match.group(1) + ",SFP")

    return "\n".join(resultado)


# =======================
# PROCESSAR IMASTER / UNM
# =======================

def processar_linhas(linhas):
    agrupado = defaultdict(list)

    for linha in linhas:

        # IMASTER / NCE
        if "Frame=" in linha:
            olt = re.search(r'\t([^\t]+)\tFrame=', linha)
            slot = re.search(r'Slot=(\d+)', linha)
            port = re.search(r'Port=(\d+)', linha)
            onu = re.search(r'ONUID=(\d+)', linha)
            password = re.search(r'Password=(\d+)', linha)
            desc = re.search(r'Description.*?=(\d+)', linha)

            if not (olt and slot and port):
                continue

            olt = olt.group(1)
            slot = int(slot.group(1))
            port = int(port.group(1))
            onu = int(onu.group(1)) if onu else 0

            if password:
                contrato = password.group(1)
            elif desc:
                contrato = desc.group(1)
            else:
                contrato = "NCE"

        # UNM2000
        elif "\t" in linha:
            col = linha.split("\t")

            if len(col) < 6:
                continue

            try:
                cliente = col[1]

                if "_" in cliente:
                    contrato = cliente.split("_")[0]
                else:
                    contrato = cliente

                slot = int(col[3])
                port = int(col[4])
                onu = int(col[5])
                olt = "OLT-UNM"

            except:
                continue

        else:
            continue

        chave = (olt, slot, port)
        agrupado[chave].append((onu, contrato))

    return agrupado


# =======================
# GERAR TICKET
# =======================

def gerar_ticket(linhas):
    gerencia = detectar_gerencia(linhas)
    data = extrair_data(linhas)

    # AMS
    if gerencia == "AMS":
        return extrair_onts_ams(linhas)

    # PRIMÁRIA PON
    if gerencia == "PRIMARIA_PON":
        portas = extrair_primaria_pon(linhas)

        return f"""-:CARIMBO DE ABERTURA - NOC:-.
Falha: Falha em rede Primaria
Hora/data: {data}
Equipamento:

Circuitos afetados:

Fone NOC 3318-7890

{portas}
"""

    # SFP
    if gerencia == "SFP":
        return extrair_sfp(linhas)

    # SECUNDÁRIA
    agrupado = processar_linhas(linhas)
    resultado = ""

    for (olt, slot, port), lista in agrupado.items():
        lista = sorted(lista, key=lambda x: x[0])

        resultado += f"""-:CARIMBO DE ABERTURA - NOC:-.
Falha: Falha em rede Secundaria, OLT: {olt}
Hora/data: {data}
Equipamento: OLT: {olt} - {slot}/{port}
Circuitos afetados: {len(lista)}

Fone NOC 3318-7890

ONUs e CONTRATOS AFETADOS:

"""

        for onu, contrato in lista:
            resultado += f"ONU {onu} - Contrato {contrato}\n"

        resultado += "\n"

    return resultado


# =======================
# INTERFACE WEB
# =======================

st.set_page_config(page_title="Gerador GPON", layout="wide")

st.title("🔧 Gerador de Alarmes GPON")

if "entrada" not in st.session_state:
    st.session_state["entrada"] = ""

if "resultado" not in st.session_state:
    st.session_state["resultado"] = ""

st.text_area(
    "Cole os alarmes aqui:",
    height=300,
    key="entrada"
)

col1, col2 = st.columns(2)

with col1:
    if st.button("🚀 Gerar Alarme"):
        if st.session_state["entrada"].strip():
            linhas = st.session_state["entrada"].split("\n")
            st.session_state["resultado"] = gerar_ticket(linhas)
        else:
            st.warning("Cole algum conteúdo primeiro.")

with col2:
    if st.button("🧹 Limpar"):
        st.session_state.clear()
        st.rerun()

if st.session_state.get("resultado"):
    st.text_area(
        "Resultado:",
        value=st.session_state["resultado"],
        height=350
    )
