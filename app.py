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

        # PRIMÁRIA CSV
        if "pon port:" in l and ".lt" in l and ".pon" in l:
            return "PRIMARIA_CSV"

        # AMS5520 ONT
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

        # UNM2000
        if "\t" in linha and ("off line" in l or "link loss" in l):
            return "UNM2000"

    return "IMASTER"


# =======================
# DETECTAR TIPO FALHA
# =======================

def detectar_tipo_falha(linhas):
    for linha in linhas:
        l = linha.lower()

        if "the feeder fiber is broken" in l:
            return "PRIMARIA"

        if "the distribute fiber is broken" in l:
            return "SECUNDARIA"

    return "SECUNDARIA"


# =======================
# EXTRAIR PRIMÁRIA CSV
# =======================

def extrair_primaria_csv(linhas):
    resultado = []

    for linha in linhas:
        linha = linha.strip()

        match = re.search(r'PON Port:([^,]+)', linha, re.IGNORECASE)
        if match:
            resultado.append(match.group(1))

    return "\n".join(resultado)


# =======================
# EXTRAIR AMS ONT
# =======================

def extrair_onts_ams(linhas):
    resultado = []

    for linha in linhas:
        linha = linha.strip()

        match = re.search(r'ONT:[^,\s]+', linha)
        if match:
            resultado.append(match.group(0))

    return "\n".join(resultado)


# =======================
# EXTRAIR AMS SFP
# =======================

def extrair_sfp_ams(linhas):
    resultado = []

    for linha in linhas:
        linha = linha.strip()

        match = re.search(r'Ethernet LT Port:([^,]+,SFP)', linha)
        if match:
            resultado.append(match.group(1))

    return "\n".join(resultado)


# =======================
# PROCESSAR LINHAS
# =======================

def processar_linhas(gerencia, linhas, data):
    agrupado = defaultdict(list)

    for linha in linhas:
        linha = linha.strip()

        if not linha:
            continue

        # ================= IMASTER =================
        if gerencia == "IMASTER":

            if "frame=" in linha.lower() and "slot=" in linha.lower() and "port=" in linha.lower():
                try:
                    olt_match = re.search(r'(olt[^\s,\t]+)', linha, re.IGNORECASE)
                    slot_match = re.search(r'Slot=(\d+)', linha, re.IGNORECASE)
                    port_match = re.search(r'Port=(\d+)', linha, re.IGNORECASE)
                    onu_match = re.search(r'ONUID=(\d+)', linha, re.IGNORECASE)

                    contrato_match = re.search(
                        r'Password=(\d+)|Description of the ONT\(only for NMS\)=(\d+)',
                        linha,
                        re.IGNORECASE
                    )

                    if not (olt_match and slot_match and port_match and onu_match):
                        continue

                    olt = olt_match.group(1)
                    slot = int(slot_match.group(1))
                    port = int(port_match.group(1))
                    onu = int(onu_match.group(1))

                    contrato = "NCE"
                    if contrato_match:
                        contrato = contrato_match.group(1) or contrato_match.group(2)

                except:
                    continue

            else:
                continue

        # ================= UNM2000 =================
        elif gerencia == "UNM2000":
            colunas = linha.split("\t")

            if len(colunas) < 6:
                continue

            try:
                cliente = colunas[1]

                if "_" in cliente:
                    contrato = cliente.split("_")[0]
                elif " " in cliente:
                    contrato = cliente.split(" ")[0]
                else:
                    contrato = cliente

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
    data = datetime.now().strftime("%d/%m/%Y %H:%M")
    tipo = detectar_tipo_falha(linhas)

    # ================= PRIMARIA =================
    if tipo == "PRIMARIA":
        olt = ""
        interfaces = []
        total_circuitos = 0

        for linha in linhas:
            linha = linha.strip()

            if not linha:
                continue

            olt_match = re.search(r'(olt[^\s,\t]+)', linha, re.IGNORECASE)
            slot_match = re.search(r'Slot=(\d+)', linha, re.IGNORECASE)
            port_match = re.search(r'Port=(\d+)', linha, re.IGNORECASE)
            afetados_match = re.search(
                r'The number of affected ONTs=(\d+)',
                linha,
                re.IGNORECASE
            )

            if olt_match:
                olt = olt_match.group(1)

            if slot_match and port_match:
                interfaces.append(
                    f"{slot_match.group(1)}/{port_match.group(1)}"
                )

            if afetados_match:
                total_circuitos += int(afetados_match.group(1))

        interfaces = sorted(set(interfaces))

        resultado = f"""-:CARIMBO DE ABERTURA - NOC:-.
Falha: Falha em rede Primaira, OLT: {olt}
Hora/data: {data}
Equipamento: OLT: {olt}

Interface: {", ".join(interfaces)}
Circuitos afetados: {total_circuitos}

Fone NOC 3318-7890


"""

        for interface in interfaces:
            slot, port = interface.split("/")
            resultado += f"Slot:{slot}/Port:{port}\n"

        return resultado

    # ================= SECUNDARIA =================
    agrupado = processar_linhas(gerencia, linhas, data)
    resultado = ""

    for chave, dados in agrupado.items():
        olt, slot, port, data = chave
        lista = sorted(dados, key=lambda x: x["onu"])

        resultado += f"""-:CARIMBO DE ABERTURA - NOC:-.
Falha: Secundaria :{olt} - {slot}/{port}
Hora/data: {data}
Circuitos Afetados: {len(lista)}


Interface: {olt} - {slot}/{port} - Secundaria

"""

        for e in lista:
            resultado += f"ONU {e['onu']} - Contrato {e['contrato']}\n"

        resultado += "\n"

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

            elif gerencia == "PRIMARIA_CSV":
                resultado = extrair_primaria_csv(linhas)

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
