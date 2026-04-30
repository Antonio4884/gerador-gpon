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

        # AMS
        if "ont:" in l and ".lt" in l and ".pon" in l:
            return "AMS"

        # UNM2000 primeiro
        if "\t" in linha and ("off line" in l or "link loss" in l):
            return "UNM2000"

        # Secundária Huawei/IMASTER (tem ONUID)
        if "onuid=" in l:
            return "IMASTER"

        # Primária Huawei
        if "los" in l and "pon port:" in l:
            return "PRIMARIA"

        if "pon port:" in l and ".lt" in l and ".pon" in l:
            return "PRIMARIA"

        if "feeder fiber is broken" in l and "onuid=" not in l:
            return "PRIMARIA"

        if "zte" in l or "com.zte" in l:
            return "ZTE"

    return "IMASTER"


# =======================
# DATA DO ALARME
# =======================

def extrair_data_alarme(linhas):
    for linha in linhas:
        match = re.search(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', linha)
        if match:
            return match.group(0)

    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def formatar_data(data_str):
    try:
        dt = datetime.strptime(data_str, "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%d/%m/%Y %H:%M")
    except:
        return data_str


# =======================
# AMS
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

            # PON Port
            match = re.search(
                r'PON Port:([A-Z0-9\-:]+).*?LT(\d+)\.PON(\d+)',
                linha,
                re.IGNORECASE
            )

            if match:
                olt = match.group(1)
                slot = int(match.group(2))
                port = int(match.group(3))
                agrupado[(olt, data)].add((slot, port))
                continue

            # Huawei frame/slot/port sem ONU
            try:
                olt_match = re.search(r'(olt[^\s\t,]+)', linha.lower())
                slot_match = re.search(r'slot=(\d+)', linha.lower())
                port_match = re.search(r'port=(\d+)', linha.lower())

                if olt_match and slot_match and port_match:
                    olt = olt_match.group(1)
                    slot = int(slot_match.group(1))
                    port = int(port_match.group(1))
                    agrupado[(olt, data)].add((slot, port))
            except:
                continue

            continue

        # ================= IMASTER / HUAWEI =================
        elif gerencia == "IMASTER":
            try:
                olt_match = re.search(r'(olt[^\s\t,]+)', linha.lower())
                slot_match = re.search(r'slot=(\d+)', linha, re.IGNORECASE)
                port_match = re.search(r'port=(\d+)', linha, re.IGNORECASE)
                onu_match = re.search(r'onuid=(\d+)', linha, re.IGNORECASE)

                contrato_match = re.search(
                    r'ONT Password=(\d+)', linha, re.IGNORECASE
                )

                if not contrato_match:
                    contrato_match = re.search(
                        r'Description of the ONT\(only for NMS\)=(\d+)',
                        linha,
                        re.IGNORECASE
                    )

                if not (
                    olt_match and
                    slot_match and
                    port_match and
                    onu_match
                ):
                    continue

                olt = olt_match.group(1)
                slot = int(slot_match.group(1))
                port = int(port_match.group(1))
                onu = int(onu_match.group(1))
                contrato = (
                    contrato_match.group(1)
                    if contrato_match else "SEM_CONTRATO"
                )

            except:
                continue

        # ================= UNM2000 =================
        elif gerencia == "UNM2000":
            colunas = linha.split("\t")

            if len(colunas) < 6:
                continue

            try:
                cliente = colunas[1]

                contrato = re.match(r'(\d+)', cliente).group(1)

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
    data = extrair_data_alarme(linhas)
    data_formatada = formatar_data(data)

    agrupado = processar_linhas(gerencia, linhas, data)

    resultado = ""

    for chave, dados in agrupado.items():
        resultado += "\n============================\n"

        # PRIMÁRIA
        if gerencia == "PRIMARIA":
            olt, _ = chave
            portas = sorted(dados)

            total = len(portas)
            slot0, port0 = portas[0]

            resultado += f"""-:CARIMBO DE ABERTURA - NOC:-.

Falha: Falha em rede Primaria, OLT: {olt}
Hora/data: {data_formatada}
Equipamento: OLT: {olt} - {slot0}/{port0}

Circuitos afetados: {total}

Fone NOC 3318-7890

OLT AFETADA:
"""

            for slot, port in portas:
                resultado += f"SLOT {slot} / PON {port}\n"

        # SECUNDÁRIA
        else:
            olt, slot, port, _ = chave
            lista = sorted(dados, key=lambda x: x["onu"])

            total = len(lista)

            resultado += f"""-:CARIMBO DE ABERTURA - NOC:-.

Falha: Falha em rede Secundaria, OLT: {olt}
Hora/data: {data_formatada}
Equipamento: OLT: {olt} - {slot}/{port}

Circuitos afetados: {total}

Fone NOC 3318-7890

ONUs e CONTRATOS AFETADOS:

"""

            for item in lista:
                resultado += (
                    f"ONU {item['onu']} - Contrato {item['contrato']}\n"
                )

    return resultado


# =======================
# STREAMLIT
# =======================

st.set_page_config(page_title="Gerador GPON", layout="wide")

st.title("🔧 Gerador de Alarmes GPON")

if "entrada" not in st.session_state:
    st.session_state["entrada"] = ""

if "resultado" not in st.session_state:
    st.session_state["resultado"] = ""

entrada = st.text_area(
    "Cole os alarmes aqui:",
    height=300,
    key="entrada"
)

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
        st.session_state["entrada"] = ""
        st.session_state["resultado"] = ""
        st.rerun()

st.text_area(
    "Resultado:",
    value=st.session_state["resultado"],
    height=350
)
