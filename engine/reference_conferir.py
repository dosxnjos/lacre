# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["pymobiledevice3==11.50.2"]
# ///
"""conferir-iphone: lê um iPhone ligado por USB (SOMENTE LEITURA) e gera um relatório HTML.

Uso: uv run conferir.py            (ou clique duas vezes em conferir.bat)
     uv run conferir.py --dados X  (refaz o relatório a partir de um .json salvo, sem aparelho)

O que faz: identidade do aparelho, travas de compra (Buscar, MDM/supervisão, perfis),
bateria, e consistência das datas de fabricação embutidas no número de série de cada peça
(câmeras, Face ID, tela, bateria) contra a data de montagem. Nada sai do PC.
Como funciona e limites: docs/README.md · armadilhas: docs/ARMADILHAS.md
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import pathlib
import re
import subprocess
import sys
import traceback
import webbrowser

AQUI = pathlib.Path(__file__).resolve().parent
SAIDA = AQUI / "relatorios"
HOJE = dt.date.today()

# Somente leitura: os ÚNICOS comandos que o script pode chamar (argumentos posicionais exatos).
COMANDOS_PERMITIDOS = {
    ("usbmux", "list"),
    ("lockdown", "info"),
    ("diagnostics", "battery", "single"),
    ("diagnostics", "ioregistry"),
    ("profile", "cloud-configuration"),
    ("profile", "list"),
}

MODELOS = {
    "iPhone10,1": "iPhone 8", "iPhone10,4": "iPhone 8", "iPhone10,2": "iPhone 8 Plus",
    "iPhone10,5": "iPhone 8 Plus", "iPhone10,3": "iPhone X", "iPhone10,6": "iPhone X",
    "iPhone11,2": "iPhone XS", "iPhone11,4": "iPhone XS Max", "iPhone11,6": "iPhone XS Max",
    "iPhone11,8": "iPhone XR", "iPhone12,1": "iPhone 11", "iPhone12,3": "iPhone 11 Pro",
    "iPhone12,5": "iPhone 11 Pro Max", "iPhone12,8": "iPhone SE (2ª geração)",
    "iPhone13,1": "iPhone 12 mini", "iPhone13,2": "iPhone 12", "iPhone13,3": "iPhone 12 Pro",
    "iPhone13,4": "iPhone 12 Pro Max", "iPhone14,4": "iPhone 13 mini", "iPhone14,5": "iPhone 13",
    "iPhone14,2": "iPhone 13 Pro", "iPhone14,3": "iPhone 13 Pro Max",
    "iPhone14,6": "iPhone SE (3ª geração)", "iPhone14,7": "iPhone 14", "iPhone14,8": "iPhone 14 Plus",
    "iPhone15,2": "iPhone 14 Pro", "iPhone15,3": "iPhone 14 Pro Max", "iPhone15,4": "iPhone 15",
    "iPhone15,5": "iPhone 15 Plus", "iPhone16,1": "iPhone 15 Pro", "iPhone16,2": "iPhone 15 Pro Max",
    "iPhone17,3": "iPhone 16", "iPhone17,4": "iPhone 16 Plus", "iPhone17,1": "iPhone 16 Pro",
    "iPhone17,2": "iPhone 16 Pro Max", "iPhone17,5": "iPhone 16e",
}
# Ano de lançamento da família (número antes da vírgula): resolve a década do dígito de ano.
ANO_FAMILIA = {7: 2014, 8: 2015, 9: 2016, 10: 2017, 11: 2018, 12: 2019, 13: 2020,
               14: 2021, 15: 2022, 16: 2023, 17: 2024, 18: 2025, 19: 2026}

PREFIXO_MODELO = {
    "M": ("verde", "vendido novo no varejo"),
    "N": ("amarelo", "aparelho de reposição da Apple (troca em garantia): é Apple, mas não é o aparelho da caixa"),
    "F": ("amarelo", "recondicionado pela Apple"),
    "P": ("verde", "vendido novo com gravação personalizada"),
    "3": ("amarelo", "unidade de demonstração de loja OU recondicionado por terceiro (fontes divergem): pergunte"),
    "5": ("amarelo", "unidade de demonstração OU recondicionado por terceiro (fontes divergem): pergunte"),
}

NOMES_PECA = {
    "BackCameraModule": "Câmera traseira (principal)",
    "BackSuperWideCameraModule": "Câmera traseira ultra-angular",
    "BackTeleCameraModule": "Câmera traseira teleobjetiva",
    "BackTelephotoCameraModule": "Câmera traseira teleobjetiva",
    "FrontCameraModule": "Câmera frontal",
    "FrontIRCameraModule": "Face ID: câmera infravermelha",
    "FrontIRStructuredLightProjector": "Face ID: projetor de pontos",
    "BackLiDARCameraModule": "Sensor LiDAR",
}
RX_CHAVE_CAMERA = re.compile(r"^(.*(?:CameraModule|Projector|LiDAR\w*))SerialNumString$")
STATUS_CAMERA = {"RomeoStatus": "Face ID: pareamento do projetor com a placa"}


# ---------------------------------------------------------------- coleta

class ErroAparelho(RuntimeError):
    pass


def pmd(*args: str, timeout: int = 180):
    posicionais = tuple(a for a in args if not a.startswith("--"))
    # tira valores de opções (--udid X, --ioclass X, --plane X)
    limpos, pular = [], False
    for a in args:
        if pular:
            pular = False
            continue
        if a.startswith("--"):
            pular = True
            continue
        limpos.append(a)
    if tuple(limpos) not in COMANDOS_PERMITIDOS:
        raise RuntimeError(f"comando fora da lista de somente leitura: {posicionais}")
    env = dict(os.environ, NO_COLOR="1", PYTHONIOENCODING="utf-8")
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pymobiledevice3", *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, env=env,
        )
    except subprocess.TimeoutExpired:
        raise ErroAparelho(f"o iPhone não respondeu em {timeout}s ({' '.join(limpos)})")
    if r.returncode != 0:
        raise ErroAparelho((r.stderr or r.stdout).strip()[-800:])
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError as e:
        raise ErroAparelho(f"saída não é JSON ({e}): {r.stdout[:300]}")


def tentar(rotulo: str, *args: str, timeout: int = 180, avisar: bool = True):
    """Coleta opcional: falha vira None + aviso, nunca derruba o relatório."""
    try:
        return pmd(*args, timeout=timeout)
    except Exception as e:  # noqa: BLE001
        if avisar:
            linha = str(e).strip().splitlines()[-1][:160] if str(e).strip() else type(e).__name__
            print(f"   ! {rotulo}: não consegui ler ({linha})")
        return None


def achar_classes(arvore, padrao: str) -> list[str]:
    achadas: list[str] = []
    rx = re.compile(padrao)

    def andar(no):
        if isinstance(no, dict):
            c = no.get("className")
            if isinstance(c, str) and rx.search(c) and c not in achadas:
                achadas.append(c)
            for f in no.get("children") or []:
                andar(f)

    andar(arvore)
    return achadas


def ler_classes(rotulo: str, classes: list[str], base: list[str]) -> dict:
    out = {}
    for c in classes:
        r = tentar(f"{rotulo} ({c})", "diagnostics", "ioregistry", "--ioclass", c, *base, avisar=False)
        if isinstance(r, dict) and r:
            out[c] = r
    return out


def coletar(udid: str) -> dict:
    base = ["--udid", udid]
    dados: dict = {"coletado_em": dt.datetime.now().isoformat(timespec="seconds")}

    print("1/6 lendo identidade do aparelho...")
    for tentativa in range(3):
        try:
            dados["info"] = pmd("lockdown", "info", *base)
            break
        except ErroAparelho as e:
            msg = str(e).strip()
            print("   ! o iPhone não respondeu:", msg.splitlines()[-1][:200] if msg else "")
            if tentativa == 2:
                raise
            input("   → Desbloqueie o iPhone, toque em 'Confiar' (e digite o código se pedir).\n"
                  "     Depois aperte Enter aqui para tentar de novo... ")

    print("2/6 lendo bateria...")
    dados["bateria"] = tentar("bateria", "diagnostics", "battery", "single", *base)

    print("3/6 mapeando o hardware (leva alguns segundos)...")
    arvore = tentar("árvore de hardware", "diagnostics", "ioregistry", "--plane", "IOService", *base, timeout=300)
    classes_cam = achar_classes(arvore, r"^AppleH\d+CamIn$")
    classes_tela = achar_classes(arvore, r"^AppleCLCD\d*$")
    dados["classes"] = {"camera": classes_cam, "tela": classes_tela}

    print("4/6 lendo número de série das peças...")
    dados["cameras"] = ler_classes("câmeras", classes_cam, base)
    if not dados["cameras"]:  # árvore falhou ou nome novo: tenta os nomes conhecidos
        dados["cameras"] = ler_classes("câmeras", [f"AppleH{n}CamIn" for n in range(9, 21)], base)
    dados["tela"] = ler_classes("tela", classes_tela, base)
    if not dados["tela"]:
        dados["tela"] = ler_classes("tela", ["AppleCLCD", "AppleCLCD2"], base)
    if not dados["cameras"]:
        print("   ! câmeras: este aparelho não expôs os números de série")
    if not dados["tela"]:
        print("   ! tela: não consegui ler a identificação")
    dados["plataforma"] = tentar("placa", "diagnostics", "ioregistry", "--ioclass", "IOPlatformExpertDevice", *base)

    print("5/6 conferindo gerenciamento (MDM/supervisão) e perfis...")
    dados["nuvem"] = tentar("supervisão", "profile", "cloud-configuration", *base)
    dados["perfis"] = tentar("perfis", "profile", "list", *base)

    return dados


# ---------------------------------------------------------------- registro de fábrica (FDR) via sysdiagnose

ARQS_FDR = ("logs/FDR/FDRDiagnosticReport.plist", "logs/BatteryHealth/BatteryHealth.log")


def coletar_fdr(udid: str, timeout: int = 900) -> dict | None:
    """Espera um sysdiagnose disparado pelos botões, baixa, extrai SÓ o registro de fábrica e a saúde
    da bateria, e apaga o pacote (no PC e no iPhone). Mesmo caminho que o 3uTools usa no iOS 17.4+."""
    import plistlib
    import tarfile
    import tempfile

    print("\nConferência de fábrica (registro FDR da Apple): leva de 5 a 10 minutos.")
    if input("Fazer agora? (s/n) ").strip().lower() not in ("s", "sim", "y"):
        return None
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="conferir-fdr-"))
    arq = tmp / "sysdiagnose.tar.gz"
    print("  → No iPhone, aperte JUNTOS os dois botões de volume e o botão lateral RAPIDINHO (menos de 1 s) e solte.\n"
          "    Ele vibra e tira um print: começou. (Se abrir a tela de desligar, cancele e tente de novo.)\n"
          "    Aguardando o iPhone gerar o diagnóstico...")
    env = dict(os.environ, NO_COLOR="1", PYTHONIOENCODING="utf-8")
    try:
        r = subprocess.run([sys.executable, "-m", "pymobiledevice3", "crash", "sysdiagnose", str(arq),
                            "--erase", "--timeout", str(timeout), "--udid", udid],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=timeout + 120, env=env)
        if r.returncode != 0 or not arq.exists():
            print("   ! não recebi o diagnóstico:", (r.stderr or r.stdout).strip()[-200:])
            return None
        out: dict = {}
        with tarfile.open(arq) as t:
            for m in t.getmembers():
                if "/._" in m.name or not m.isfile():
                    continue
                for alvo in ARQS_FDR:
                    if m.name.endswith(alvo):
                        out[alvo] = t.extractfile(m).read()
        res: dict = {"tem_fdr": ARQS_FDR[0] in out}
        if res["tem_fdr"]:
            res["fdr"] = json.loads(json.dumps(plistlib.loads(out[ARQS_FDR[0]]), default=lambda b: b.hex() if isinstance(b, bytes) else str(b)))
        if ARQS_FDR[1] in out:
            txt = out[ARQS_FDR[1]].decode("utf-8", "replace")
            m = re.search(r'"Maximum Capacity Percent"\s*=\s*(\d+)', txt)
            res["saude_bateria_oficial"] = int(m.group(1)) if m else None
        print("   ✓ registro de fábrica lido" if res["tem_fdr"] else "   ! o diagnóstico veio sem registro de fábrica")
        return res
    except subprocess.TimeoutExpired:
        print("   ! o iPhone não terminou o diagnóstico a tempo")
        return None
    finally:
        for p in tmp.glob("*"):
            try:
                p.unlink()
            except OSError:
                pass
        try:
            tmp.rmdir()
        except OSError:
            pass


# Classes do FDR (nomes de 4 letras da Apple). Mapeamento parcial, só onde o conteúdo confirma.
NOMES_FDR = {
    "vcrt": "Bateria", "bat#": "Bateria (nº de série)", "tcrt": "Tela (touch)", "GpCl": "Tela",
    "drp#": "Tela (identificação do painel)", "mlb#": "Placa principal", "SrNm": "Número de série",
    "imei": "IMEI", "ime2": "IMEI 2", "WMac": "Wi-Fi", "BMac": "Bluetooth",
}


def avaliar_fdr(fdr_res: dict | None) -> dict | None:
    if not fdr_res:
        return None
    if not fdr_res.get("tem_fdr"):
        return {"linhas": [("amarelo", "Registro de fábrica", "o diagnóstico não trouxe o registro (FDR)", "")],
                "selado": None, "ok": False, "falhas": 0, "verificados": 0,
                "saude": fdr_res.get("saude_bateria_oficial")}
    f = d_(fdr_res.get("fdr"))
    linhas, falhas = [], 0

    def itens(lista):
        for x in lista or []:
            for k, v in d_(x).items():
                yield k, d_(v)

    verificados = [k for k, _ in itens(f.get("VerifiedData"))] + [k for k, _ in itens(f.get("VerifiedProperties"))]
    for secao, campo in (("FailureData", "Instance"), ("FailureProperties", "Property")):
        for k, v in itens(f.get(secao)):
            viva, selada = v.get("Live" + campo), v.get("Sealed" + campo)
            aviso = str(v.get("WarningMessage", ""))
            nome = NOMES_FDR.get(k, f"componente {k}")
            if selada is not None and viva != selada:
                falhas += 1
                linhas.append(("vermelho", nome, "DIFERENTE do selado na fábrica",
                               f"selado: {selada} · instalado: {viva if viva is not None else 'ausente'} → peça trocada"))
            elif "not required to seal" in aviso:
                continue  # chave que a Apple não sela: informativo
            else:
                falhas += 1
                linhas.append(("amarelo", nome, "não verificado", aviso or "falha sem detalhe"))
    if f.get("DataFailedToReport"):
        linhas.append(("amarelo", "Registro de fábrica", "parte dos dados não foi reportada", str(f.get("DataFailedToReport"))[:200]))
    if f.get("ApTicket") not in (None, "Trusted"):
        linhas.append(("amarelo", "Ticket do sistema", str(f.get("ApTicket")), ""))
    nomeados = sorted({NOMES_FDR[k] for k in verificados if k in NOMES_FDR})
    linhas.insert(0, ("verde" if not falhas else "vermelho", "Peças conferidas com o registro de fábrica",
                      f"{len(verificados)} itens verificados, {falhas} com problema",
                      "Inclui: " + ", ".join(nomeados) + " e outros componentes que a Apple sela (câmeras, "
                      "Face ID, etc., conforme o modelo)." if nomeados else ""))
    return {"linhas": linhas, "selado": f.get("SealDate"), "ok": not falhas, "falhas": falhas,
            "verificados": len(verificados), "saude": fdr_res.get("saude_bateria_oficial")}


# ---------------------------------------------------------------- decodificação

ANO_LETRAS = "CDFGHJKLMNPQRSTVWXYZ"           # 4º caractere do serial antigo: ano + metade
SEMANA_LETRAS = "123456789CDFGHJKLMNPQRTVWXY"  # 5º caractere: semana dentro da metade (1–27)
# Tabelas conferidas contra o macserial do OpenCore (AppleYearReverse / AppleTblWeek).


def piso_ano(tipo: str) -> int:
    """Primeiro ano plausível de fabricação de peça para este modelo (lançamento − 1)."""
    m = re.match(r"^iPhone(\d+),", tipo or "")
    if m and int(m.group(1)) in ANO_FAMILIA:
        return ANO_FAMILIA[int(m.group(1))] - 1
    return HOJE.year - 9


def resolver_ano(digito: int, piso: int) -> int | None:
    """Dígito único de ano → o único ano em [piso, piso+9] terminado nele; None se cair no futuro."""
    for ano in range(piso, piso + 10):
        if ano % 10 == digito:
            return ano if ano <= HOJE.year else None
    return None


def semana_para_data(ano: int | None, semana: int) -> dt.date | None:
    if not ano:
        return None
    for s in (semana, 52):
        try:
            d = dt.date.fromisocalendar(ano, s, 1)
            return d if d <= HOJE + dt.timedelta(days=14) else None
        except ValueError:
            continue
    return None


def data_serial_antigo(sn: str, piso: int) -> dt.date | None:
    """Serial de 12 caracteres (aparelhos feitos até ~maio/2021): 4º = ano+metade, 5º = semana.
    Os aleatórios (8–14 caracteres, normalmente 10) não têm data."""
    if not sn or len(sn) != 12:
        return None
    a, w = sn[3], sn[4]
    if a not in ANO_LETRAS or w not in SEMANA_LETRAS:
        return None
    i = ANO_LETRAS.index(a)
    semana = SEMANA_LETRAS.index(w) + 1 + 26 * (i % 2)
    return semana_para_data(resolver_ano(i // 2, piso), semana)


RX_PECA = re.compile(r"^[A-Z0-9]{3}(\d)(\d{2})[A-Z0-9]")


def data_serial_peca(sn, piso: int) -> dt.date | None:
    """Serial de peça/placa no formato PPP Y WW…: fornecedor (3) + ano (1 dígito) + semana (2)."""
    sn = hex_texto(sn)
    if not sn:
        return None
    m = RX_PECA.match(sn.strip().upper())
    if not m:
        return None
    semana = int(m.group(2))
    if not 1 <= semana <= 53:
        return None
    return semana_para_data(resolver_ano(int(m.group(1)), piso), semana)


def hex_texto(v) -> str | None:
    if isinstance(v, dict) and "$hex" in v:
        try:
            t = bytes.fromhex(v["$hex"]).split(b"\x00")[0].decode("utf-8", "replace").strip()
            return t if t and t.isprintable() else None
        except ValueError:
            return None
    return v.strip() if isinstance(v, str) and v.strip() else None


def d_(v) -> dict:
    return v if isinstance(v, dict) else {}


def mes_ano(d: dt.date | None) -> str:
    if not d:
        return "—"
    meses = "jan fev mar abr mai jun jul ago set out nov dez".split()
    return f"{meses[d.month - 1]}/{d.year}"


# ---------------------------------------------------------------- avaliação

def avaliar(dados: dict) -> dict:
    info = d_(dados.get("info"))
    plat = d_(dados.get("plataforma"))
    bat = d_(dados.get("bateria"))
    bd = d_(bat.get("BatteryData"))
    itens_compra, pecas, avisos, bateria = [], [], [], {}
    cobertura = {"camera": False, "tela": False, "bateria": False}

    tipo = str(info.get("ProductType", "?"))
    piso = piso_ano(tipo)
    modelo_num = hex_texto(info.get("ModelNumber")) or hex_texto(plat.get("model-number")) or "?"
    sn = hex_texto(info.get("SerialNumber")) or hex_texto(plat.get("serial-number")) or ""
    mlb = hex_texto(info.get("MLBSerialNumber")) or hex_texto(plat.get("mlb-serial-number")) or ""
    ident = {
        "Aparelho": f"{MODELOS.get(tipo, tipo)} ({tipo})",
        "Nome no aparelho": info.get("DeviceName", "?"),
        "iOS": f"{info.get('ProductVersion', '?')} ({info.get('BuildVersion', '?')})",
        "Modelo de venda": f"{modelo_num} · região {info.get('RegionInfo', '?')}",
        "Número de série": sn or "?",
        "IMEI": info.get("InternationalMobileEquipmentIdentity", "—"),
        "IMEI 2": info.get("InternationalMobileEquipmentIdentity2", "—"),
    }

    # --- âncora: quando o aparelho foi montado (a mais tardia entre placa e serial)
    d_placa = data_serial_peca(mlb, piso)
    d_serial = data_serial_antigo(sn, piso)
    if d_serial and (not d_placa or d_serial >= d_placa):
        ancora, fonte_ancora = d_serial, "montagem (número de série)"
    elif d_placa:
        ancora, fonte_ancora = d_placa, "placa principal"
    else:
        ancora, fonte_ancora = None, None
    if d_placa and d_serial and abs((d_serial - d_placa).days) > 120:
        avisos.append(f"A data da placa ({mes_ano(d_placa)}) e a do número de série ({mes_ano(d_serial)}) "
                      "estão a mais de 4 meses de distância. A placa pode ter sido trocada, ou a "
                      "leitura das datas não vale para este modelo.")
    if not ancora:
        avisos.append("Não consegui datar a montagem do aparelho: a comparação de datas das peças ficou sem referência.")

    # --- travas de compra
    nvram = d_(info.get("NonVolatileRAM"))
    buscar = (hex_texto(nvram.get("fm-activation-locked")) or "").upper()
    conta = hex_texto(nvram.get("fm-account-masked"))
    if buscar == "YES":
        itens_compra.append(("vermelho", "Buscar iPhone / Bloqueio de Ativação", "LIGADO" + (f" (conta {conta})" if conta else ""),
                             "Antes de pagar: o vendedor sai da conta iCloud (Ajustes → nome → Sair) e apaga o "
                             "aparelho na sua frente. Com o Buscar ligado, o iPhone fica preso à conta dele."))
    elif buscar == "NO":
        itens_compra.append(("verde", "Buscar iPhone / Bloqueio de Ativação", "desligado", ""))
    else:
        itens_compra.append(("amarelo", "Buscar iPhone / Bloqueio de Ativação", "não consegui ler",
                             "Confira no aparelho: Ajustes → nome do usuário → Buscar."))

    nuvem = dados.get("nuvem")
    if not isinstance(nuvem, dict) or not nuvem:
        itens_compra.append(("amarelo", "Gerenciamento por empresa (MDM)", "não consegui ler",
                             "Confira em Ajustes → Geral → VPN e Gerenciamento de Dispositivos."))
    else:
        org = nuvem.get("OrganizationName")
        if nuvem.get("IsSupervised") or nuvem.get("IsMDMUnremovable") or org:
            itens_compra.append(("vermelho", "Gerenciamento por empresa (MDM)", f"SIM{(' · ' + str(org)) if org else ''}",
                                 "Aparelho de empresa ou escola: pode voltar a ser bloqueado depois de formatado. Não compre."))
        elif nuvem.get("ConfigurationSource", 0) not in (0, None):
            itens_compra.append(("amarelo", "Gerenciamento por empresa (MDM)",
                                 f"configuração em nuvem presente (origem {nuvem.get('ConfigurationSource')})",
                                 "Pode ser de empresa. Confira em Ajustes → Geral → VPN e Gerenciamento de Dispositivos."))
        else:
            itens_compra.append(("verde", "Gerenciamento por empresa (MDM)", "não gerenciado", ""))

    perfis = dados.get("perfis")
    lista_perfis = []
    if isinstance(perfis, dict):
        lista_perfis = [p for p in d_(perfis.get("ProfileMetadata")).values() if isinstance(p, dict)]
    elif isinstance(perfis, list):
        lista_perfis = [p for p in perfis if isinstance(p, dict)]
    if perfis is None:
        itens_compra.append(("amarelo", "Perfis de configuração instalados", "não consegui ler",
                             "Confira em Ajustes → Geral → VPN e Gerenciamento de Dispositivos."))
    elif lista_perfis:
        nomes = ", ".join(str(p.get("PayloadDisplayName", "?")) for p in lista_perfis)
        itens_compra.append(("amarelo", "Perfis de configuração instalados", f"{len(lista_perfis)}: {nomes}",
                             "Pode ser inofensivo (ex.: DNS), mas peça para remover antes: Ajustes → Geral → VPN e Gerenciamento."))
    else:
        itens_compra.append(("verde", "Perfis de configuração instalados", "nenhum", ""))

    estado = info.get("ActivationState", "?")
    itens_compra.append(("verde" if estado == "Activated" else "amarelo", "Ativação", estado, ""))

    cor, txt = PREFIXO_MODELO.get(modelo_num[:1], ("amarelo", "prefixo desconhecido: pergunte a origem"))
    itens_compra.append((cor, "Origem (prefixo do modelo de venda)", f"{modelo_num[:1]} → {txt}",
                         "Leitura da comunidade; a Apple não publica o significado dos prefixos."))

    # --- peças
    def julgar(nome: str, serial, chave: str | None = None) -> None:
        serial = hex_texto(serial)
        if not serial:
            pecas.append(("cinza", nome, "—", "—", "sem número de série legível"))
            return
        d = data_serial_peca(serial, piso)
        if not d:
            pecas.append(("cinza", nome, serial, "—", "data não decodificável neste formato"))
            return
        if chave:
            cobertura[chave] = True
        if not ancora:
            pecas.append(("cinza", nome, serial, mes_ano(d), "sem data de montagem para comparar"))
            return
        semanas = (d - ancora).days / 7
        if semanas > 26:
            pecas.append(("vermelho", nome, serial, mes_ano(d),
                          f"fabricada ~{round(semanas / 4.35)} meses DEPOIS da {fonte_ancora}: provável troca "
                          "(confira em Histórico de Peças e Serviços)"))
        elif semanas > 10:
            pecas.append(("amarelo", nome, serial, mes_ano(d),
                          f"fabricada ~{round(semanas)} semanas depois da {fonte_ancora}: possível troca, confira"))
        elif semanas < -78:
            pecas.append(("amarelo", nome, serial, mes_ano(d),
                          f"~{round(-semanas / 4.35)} meses mais antiga que a {fonte_ancora}: incomum, vale conferir"))
        else:
            pecas.append(("verde", nome, serial, mes_ano(d), "data coerente com a montagem"))

    cam_props: dict = {}
    for v in d_(dados.get("cameras")).values():
        cam_props.update(d_(v))
    for k, v in sorted(cam_props.items()):
        m = RX_CHAVE_CAMERA.match(k)
        if m:
            julgar(NOMES_PECA.get(m.group(1), m.group(1)), v, "camera")
    if not any(RX_CHAVE_CAMERA.match(k) for k in cam_props):
        pecas.append(("amarelo", "Câmeras e Face ID", "—", "—",
                      "não consegui ler os números de série das câmeras neste aparelho: confira no próprio iPhone"))
    for k, nome in STATUS_CAMERA.items():
        v = hex_texto(cam_props.get(k))
        if v:
            ok = v.lower() in ("valid", "ok", "success")
            pecas.append(("verde" if ok else "amarelo", nome, v, "—",
                          "pareado com a placa" if ok else "estado inesperado: teste o Face ID na hora"))

    painel = None
    for v in d_(dados.get("tela")).values():
        for k, val in d_(v).items():
            if re.search(r"panel.?id", k, re.I):
                painel = hex_texto(val) or painel
    if painel:
        tokens = [t for t in painel.split("+") if t]
        validos = [t for t in tokens if data_serial_peca(t, piso)]
        if not validos:
            pecas.append(("amarelo", "Tela", painel[:40] + "…", "—",
                          "a tela tem identificação, mas nenhum trecho com data legível: confira no próprio iPhone"))
        for i, t in enumerate(validos, 1):
            julgar(f"Tela: componente {i} de {len(validos)}", t, "tela")
    else:
        pecas.append(("amarelo", "Tela", "—", "—",
                      "não consegui ler a identificação da tela (pode ser tela paralela ou o modelo não expõe): confira no iPhone"))
    if not any(k in cam_props for k in STATUS_CAMERA) and tipo in ("iPhone12,8", "iPhone14,6"):
        pecas.append(("cinza", "Touch ID", "—", "—", "o pareamento do Touch ID não é conferido aqui: teste na hora"))

    # --- bateria (estimativas: não entram no veredito; o número oficial é o de Ajustes)
    julgar("Bateria", bd.get("Serial") or bat.get("Serial"), "bateria")
    projeto = bd.get("DesignCapacity") or bat.get("DesignCapacity")
    nominal = bat.get("NominalChargeCapacity")
    bruta = bat.get("AppleRawMaxCapacity")
    ciclos = bd.get("CycleCount") if bd.get("CycleCount") is not None else bat.get("CycleCount")
    horas = d_(bd.get("LifetimeData")).get("TotalOperatingTime")
    if isinstance(projeto, (int, float)) and projeto > 0 and (nominal or bruta):
        partes = []
        if isinstance(nominal, (int, float)):
            partes.append(f"~{round(100 * nominal / projeto)}% (carga nominal {nominal} de {projeto} mAh)")
        if isinstance(bruta, (int, float)):
            partes.append(f"~{round(100 * bruta / projeto)}% (capacidade bruta {bruta} mAh)")
        bateria["Saúde estimada"] = ("cinza", " · ".join(partes),
                                     "Estimativa. O número oficial é o de Ajustes → Bateria → Saúde; abaixo de 80% "
                                     "ou com o aviso 'significativamente degradada', a bateria pede troca.")
    if ciclos is not None:
        bateria["Ciclos de carga"] = ("cinza", str(ciclos),
                                      "A Apple projeta 80% de capacidade com 500 ciclos (iPhone 14 e anteriores) "
                                      "ou 1000 ciclos (iPhone 15).")
    if isinstance(horas, (int, float)) and horas > 0 and ancora:
        idade_d = max(1, (HOJE - ancora).days)
        anos_bat, anos_ap = horas / 24 / 365.25, idade_d / 365.25
        if idade_d > 365 and horas / (idade_d * 24) < 0.5:
            bateria["Tempo de uso da bateria"] = ("amarelo", f"~{anos_bat:.1f} anos ligada",
                                                  f"O aparelho tem ~{anos_ap:.1f} anos. A bateria parece bem mais nova "
                                                  "que ele: provável troca (ou ficou muito tempo guardado).")
        else:
            bateria["Tempo de uso da bateria"] = ("verde", f"~{anos_bat:.1f} anos ligada",
                                                  f"Coerente com a idade do aparelho (~{anos_ap:.1f} anos).")
    if isinstance(ciclos, int) and ciclos < 100 and ancora and (HOJE - ancora).days > 2 * 365:
        avisos.append("Bateria com poucos ciclos num aparelho com mais de 2 anos: provável troca recente. "
                      "Confira o Histórico de Peças e Serviços.")

    return {
        "ident": ident, "ancora": ancora, "fonte_ancora": fonte_ancora, "compra": itens_compra,
        "pecas": pecas, "bateria": bateria, "avisos": avisos, "cobertura": cobertura,
        "imeis": [x for x in (info.get("InternationalMobileEquipmentIdentity"),
                              info.get("InternationalMobileEquipmentIdentity2")) if x],
        "modelo": MODELOS.get(tipo, tipo), "serial": sn, "nome": info.get("DeviceName", "?"),
    }


# ---------------------------------------------------------------- relatório

CSS = """
:root{--bg:#f6f5f2;--card:#fff;--tx:#1d1d1f;--mut:#6b6b70;--ln:#e3e1dc;
--verde:#1f7a3a;--verde-bg:#e6f4ea;--amarelo:#8a5a00;--amarelo-bg:#fdf3dc;
--vermelho:#b42318;--vermelho-bg:#fdecea;--cinza:#5f6368;--cinza-bg:#eef0f2}
@media (prefers-color-scheme:dark){:root{--bg:#141416;--card:#1f1f22;--tx:#ececef;--mut:#a0a0a8;--ln:#333338;
--verde:#6fd08c;--verde-bg:#16301f;--amarelo:#f0c060;--amarelo-bg:#33290f;--vermelho:#ff8a80;--vermelho-bg:#3a1714;
--cinza:#b0b4ba;--cinza-bg:#2a2b2e}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);
font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:960px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:26px;margin:0 0 4px}h2{font-size:18px;margin:32px 0 10px}
.sub{color:var(--mut);margin:0 0 16px}
.qual{font-size:20px;font-weight:700;margin:8px 0 0}
.resumo{padding:16px 18px;border-radius:12px;margin:16px 0;font-size:17px;font-weight:600}
.card{background:var(--card);border:1px solid var(--ln);border-radius:12px;overflow:hidden}
table{width:100%;border-collapse:collapse}td,th{padding:10px 12px;border-top:1px solid var(--ln);text-align:left;vertical-align:top}
tr:first-child td,tr:first-child th{border-top:0}th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--mut)}
.mono{font-family:ui-monospace,Consolas,monospace;font-size:13px;word-break:break-all}
.tag{display:inline-block;padding:2px 8px;border-radius:99px;font-size:12px;font-weight:700;white-space:nowrap}
.verde{color:var(--verde);background:var(--verde-bg)}.amarelo{color:var(--amarelo);background:var(--amarelo-bg)}
.vermelho{color:var(--vermelho);background:var(--vermelho-bg)}.cinza{color:var(--cinza);background:var(--cinza-bg)}
.nota{color:var(--mut);font-size:13px}ol li,ul li{margin:6px 0}a{color:inherit}
@media (max-width:640px){td,th{padding:8px}.esconde{display:none}}
"""
ROTULO = {"verde": "OK", "amarelo": "ATENÇÃO", "vermelho": "ALERTA", "cinza": "N/V"}


def e(x) -> str:
    return html.escape(str(x))


def tag(cor: str) -> str:
    return f'<span class="tag {cor}">{ROTULO[cor]}</span>'


def veredito(r: dict) -> tuple[str, str]:
    fdr = r.get("fdr")
    cores = [c for c, *_ in r["compra"]] + [c for c, *_ in r["pecas"]] + \
            [v[0] for v in r["bateria"].values()] + [c for c, *_ in (fdr or {}).get("linhas", [])]
    if "vermelho" in cores:
        return "vermelho", "Há ALERTAS. Leia os itens em vermelho antes de pagar."
    if fdr and fdr["ok"] and fdr["verificados"]:
        if "amarelo" in cores or r["avisos"]:
            return "amarelo", ("Registro de fábrica da Apple confere (nenhuma peça diferente da selada), "
                               "mas há pontos de atenção.")
        return "verde", ("Registro de fábrica da Apple confere: nenhuma peça diferente da selada na fábrica. "
                         "Faça também a conferência no próprio iPhone e o teste rápido.")
    faltou = [n for n, ok in (("câmeras", r["cobertura"]["camera"]), ("tela", r["cobertura"]["tela"]),
                              ("bateria", r["cobertura"]["bateria"])) if not ok]
    if not r["ancora"] or faltou:
        extra = f" (não consegui datar: {', '.join(faltou)})" if faltou else ""
        return "amarelo", ("Conferência das peças INCOMPLETA" + extra +
                           ". Faça a conferência no próprio iPhone (lista abaixo) e rode o 3uTools como segunda opinião.")
    if "amarelo" in cores or r["avisos"]:
        return "amarelo", "Nada grave encontrado, mas há pontos de atenção."
    return "verde", ("Datas das peças coerentes e sem travas. Isso não prova que nada foi trocado "
                     "(peça usada da mesma época passa): faça também a conferência no próprio iPhone.")


def secao_fdr(fdr: dict | None) -> str:
    cab = "<h2>Registro de fábrica da Apple (FDR)</h2>"
    if not fdr:
        return (cab + '<div class="card" style="padding:12px 16px">Não feito nesta leitura. É a conferência mais forte: '
                "rode de novo e responda <b>s</b> quando perguntar (leva de 5 a 10 minutos).</div>")
    nota = ('<p class="nota">O iPhone guarda, selado na fábrica, o número de cada peça original. O diagnóstico do próprio '
            "iPhone compara com as peças instaladas agora: é o mesmo dado que o 3uTools lê no iOS novo.")
    if fdr.get("selado"):
        nota += f" Selado em <b>{e(fdr['selado'])}</b>."
    if fdr.get("saude") is not None:
        nota += f" Saúde oficial da bateria (a mesma de Ajustes): <b>{e(fdr['saude'])}%</b>."
    nota += "</p>"
    linhas = "".join(f"<tr><td>{tag(c)}</td><td><b>{e(n)}</b><br>{e(v)}"
                     f"{('<div class=nota>' + e(d) + '</div>') if d else ''}</td></tr>" for c, n, v, d in fdr["linhas"])
    return cab + nota + f'<div class="card"><table>{linhas}</table></div>'


def montar_html(r: dict) -> str:
    cor_res, txt_res = veredito(r)
    linhas_id = "".join(f"<tr><th>{e(k)}</th><td class='mono'>{e(v)}</td></tr>" for k, v in r["ident"].items())
    anc = (f"{mes_ano(r['ancora'])} (pela {r['fonte_ancora']})" if r["ancora"]
           else "não consegui datar: as peças ficaram sem referência")
    linhas_id += f"<tr><th>Montagem estimada</th><td>{e(anc)}</td></tr>"

    def tabela_itens(itens):
        return "".join(f"<tr><td>{tag(c)}</td><td><b>{e(n)}</b><br>{e(v)}"
                       f"{('<div class=nota>' + e(d) + '</div>') if d else ''}</td></tr>" for c, n, v, d in itens)

    linhas_pecas = "".join(
        f"<tr><td>{tag(c)}</td><td><b>{e(n)}</b><div class=nota>{e(d)}</div></td>"
        f"<td>{e(f)}</td><td class='mono esconde'>{e(s)}</td></tr>" for c, n, s, f, d in r["pecas"])
    linhas_bat = "".join(f"<tr><td>{tag(c)}</td><td><b>{e(k)}</b><br>{e(v)}<div class=nota>{e(d)}</div></td></tr>"
                         for k, (c, v, d) in r["bateria"].items())
    avisos = "".join(f"<li>{e(a)}</li>" for a in r["avisos"])
    imeis = " e ".join(e(x) for x in r["imeis"]) or "—"
    final4 = e(r["serial"][-4:]) if r["serial"] else "?"

    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Conferência do iPhone</title>
<style>{CSS}</style></head><body><main>
<h1>Conferência: {e(r['modelo'])}</h1>
<p class="qual">Aparelho lido: “{e(r['nome'])}” · série terminada em {final4}</p>
<p class="sub">Confira que é o aparelho do vendedor. Gerado em {e(dt.datetime.now().strftime('%d/%m/%Y %H:%M'))}
· leitura direta por USB, nada saiu do PC.</p>
<div class="resumo {cor_res}">{e(txt_res)}</div>
{('<div class="card" style="padding:4px 16px"><ul>' + avisos + '</ul></div>') if avisos else ''}

<h2>Antes de pagar (travas)</h2>
<div class="card"><table>{tabela_itens(r['compra'])}</table></div>

{secao_fdr(r.get('fdr'))}

<h2>Peças: as datas batem com a montagem?</h2>
<p class="nota">Cada peça traz no número de série o ano e a semana em que foi fabricada (padrão observado, não documentado
pela Apple). No aparelho original, todas são de semanas ou meses <b>antes</b> da montagem. Peça bem <b>depois</b> da montagem
foi trocada (por original ou não). Limites: peça usada tirada de outro iPhone da mesma época passa como OK; bateria
com células trocadas mas placa de controle original também passa.</p>
<div class="card"><table><tr><th></th><th>Peça</th><th>Fabricada</th><th class="esconde">Nº de série</th></tr>{linhas_pecas}</table></div>

<h2>Bateria</h2>
<div class="card"><table>{linhas_bat or '<tr><td>não consegui ler a bateria</td></tr>'}</table></div>

<h2>Aparelho</h2>
<div class="card"><table>{linhas_id}</table></div>

<h2>Confira no próprio iPhone (2 minutos)</h2>
<div class="card" style="padding:4px 20px"><ol>
<li><b>Ajustes → Geral → Sobre → Histórico de Peças e Serviço(s).</b> Se a seção não aparece, nenhuma das peças que a Apple
rastreia <i>neste modelo</i> foi registrada como trocada: no XR, XS e SE 2/3 só a bateria; no 11, bateria e tela; do 12 em
diante, bateria, tela, placa, câmera frontal e traseiras. O resto (Face ID no 11, tampa, alto-falante, conector) a Apple não
rastreia. Rótulos: <b>Genuína/Original</b> = trocada por peça Apple; <b>Desconhecida</b> = paralela ou não verificada;
<b>Usada</b> = peça Apple vinda de outro iPhone; <b>Não verificada</b> (placa) = placa trocada. A mensagem de bateria
"significativamente degradada" é aviso de desgaste, não de troca.</li>
<li><b>Ajustes → Bateria → Saúde:</b> tem que mostrar a porcentagem, e não "Não é possível verificar se este iPhone tem uma
bateria genuína da Apple". Do iPhone 15 em diante a mesma tela mostra a data de fabricação e de primeiro uso da bateria.</li>
<li><b>Disque *#06#</b>: os IMEIs têm que ser os mesmos daqui ({imeis}), da caixa e da nota.</li>
<li><b>Consulte se algum IMEI tem bloqueio</b> por roubo ou perda (os dois, se houver dois):
<a href="https://www.gov.br/anatel/pt-br/consumidor/situacao-do-celular-imei">Anatel: situação do celular</a> ·
<a href="https://www.consultaaparelhoimpedido.com.br">consultaaparelhoimpedido.com.br</a>. Sites de IMEI de terceiros não valem.</li>
<li><b>Garantia e modelo pelo número de série:</b> <a href="https://checkcoverage.apple.com">checkcoverage.apple.com</a>.</li>
<li><b>Segunda opinião:</b> rode o 3uTools neste PC (Relatório de Verificação). Nunca aceite print de relatório mandado pelo vendedor.</li>
<li><b>Na hora de fechar:</b> o vendedor sai do iCloud, apaga o aparelho (Ajustes → Geral → Transferir ou Redefinir → Apagar)
e você configura com a sua conta antes de pagar.</li>
<li><b>Teste rápido:</b> Face ID ou Touch ID, todas as câmeras, alto-falante, microfone (grave um áudio), carregamento,
tela inteira (imagem branca, procure mancha), botões, chip da operadora.</li>
</ol></div>
<p class="nota">Relatório com IMEI e número de série: guarde só no seu PC. Ferramenta: C:\\Dev\\conferir-iphone (somente leitura).</p>
</main></body></html>"""


# ---------------------------------------------------------------- main

def escolher_aparelho(pedido: str | None) -> str | None:
    print("Procurando iPhone ligado por USB...")
    try:
        lista = pmd("usbmux", "list")
    except ErroAparelho as ex:
        print("Não consegui falar com o serviço da Apple no PC. O app 'Apple Devices' (ou iTunes) está instalado?\n", ex)
        return None
    usb = [d for d in lista if isinstance(d, dict) and d.get("ConnectionType") == "USB"]
    if pedido:
        usb = [d for d in usb if pedido in (d.get("UniqueDeviceID"), d.get("Identifier"))]
    if not usb:
        print("Nenhum iPhone encontrado pelo cabo. Confira o cabo (de dados, não só de carga), use uma porta USB "
              "de trás do PC, desbloqueie o iPhone e toque em 'Confiar'.")
        return None
    if len(usb) > 1:
        for i, d in enumerate(usb, 1):
            print(f"  {i}) {d.get('DeviceName')} ({d.get('ProductType')})")
        while True:
            n = input("Mais de um iPhone ligado. Qual conferir? Número: ").strip()
            if n.isdigit() and 1 <= int(n) <= len(usb):
                usb = [usb[int(n) - 1]]
                break
    d = usb[0]
    print(f"Achei: {d.get('DeviceName')} ({d.get('ProductType')}, iOS {d.get('ProductVersion')})")
    return d.get("UniqueDeviceID") or d.get("Identifier")


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dados", help="refaz o relatório a partir de um .json salvo")
    ap.add_argument("--udid", help="escolhe o aparelho quando há mais de um ligado")
    ap.add_argument("--saida", help="pasta do relatório (padrão: relatorios/)")
    ap.add_argument("--sem-abrir", action="store_true", help="não abre o navegador no fim")
    ap.add_argument("--sem-fabrica", action="store_true", help="pula a conferência do registro de fábrica (sysdiagnose)")
    a = ap.parse_args()
    saida = pathlib.Path(a.saida) if a.saida else SAIDA

    if a.dados:
        dados = json.loads(pathlib.Path(a.dados).read_text(encoding="utf-8"))
    else:
        udid = escolher_aparelho(a.udid)
        if not udid:
            return 1
        try:
            dados = coletar(udid)
        except ErroAparelho as ex:
            print("\nNão consegui ler o iPhone. Desbloqueie, toque em 'Confiar', confira o cabo e rode de novo.\n", ex)
            return 1
        if not a.sem_fabrica:
            dados["fabrica"] = coletar_fdr(udid)
        print("montando o relatório...")

    saida.mkdir(parents=True, exist_ok=True)
    carimbo = dt.datetime.now().strftime("%Y-%m-%d-%H%M")
    try:
        r = avaliar(dados)
        r["fdr"] = avaliar_fdr(dados.get("fabrica"))
    except Exception:  # noqa: BLE001  relatório parcial em vez de traceback
        erro = traceback.format_exc()
        print("\n! erro ao interpretar os dados:\n", erro)
        r = {"ident": {}, "ancora": None, "fonte_ancora": None, "compra": [], "bateria": {},
             "pecas": [("amarelo", "Erro ao interpretar a leitura", "—", "—", erro.strip().splitlines()[-1])],
             "avisos": ["A leitura foi feita, mas o script não soube interpretar algum dado deste modelo. "
                        "Os dados brutos estão no .json ao lado. Use a conferência no iPhone e o 3uTools."],
             "cobertura": {"camera": False, "tela": False, "bateria": False}, "imeis": [],
             "modelo": str(d_(dados.get("info")).get("ProductType", "iPhone")), "serial": "", "nome": "?"}
    nome = re.sub(r"[^A-Za-z0-9]+", "-", f"{carimbo}-{r['modelo']}-{r['serial'][-4:]}").strip("-")
    if not a.dados:
        (saida / f"{nome}.json").write_text(json.dumps(dados, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    destino = saida / f"{nome}.html"
    destino.write_text(montar_html(r), encoding="utf-8")
    cor, txt = veredito(r)
    print(f"\n[{ROTULO[cor]}] {txt}\nRelatório: {destino}")
    for c, n, v, _ in r["compra"]:
        print(f"  [{ROTULO[c]:>8}] {n}: {v}")
    for c, n, s, f, d in r["pecas"]:
        print(f"  [{ROTULO[c]:>8}] {n} ({f}): {d}")
    if not a.sem_abrir:
        webbrowser.open(destino.as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
