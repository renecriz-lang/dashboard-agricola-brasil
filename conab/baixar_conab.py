"""
baixar_conab.py
===============================================================================
Acessa o site da CONAB, verifica se há um novo boletim mensal publicado e
baixa o XLSX se for inédito. Após o download, chama etl_conab.py.

Arquivos gerados:
    conab/raw/conab_atual.xlsx      — XLSX atual (sobrescrito a cada novo boletim)
    conab/raw/ultimo_baixado.txt    — controle de versão (nome do XLSX baixado)

Uso:
    python conab/baixar_conab.py    (a partir da raiz do repositório)

Dependências:
    pip install requests beautifulsoup4
===============================================================================
"""

from pathlib import Path
from datetime import datetime
from urllib.parse import urljoin, urlparse
import subprocess
import sys
import requests
from bs4 import BeautifulSoup


# ----------------------------------------------------------------------
# Configuração
# ----------------------------------------------------------------------

URL_LISTAGEM = (
    "https://www.gov.br/conab/pt-br/atuacao/informacoes-agropecuarias/"
    "safras/safra-de-graos/boletim-da-safra-de-graos/boletim-da-safra-de-graos"
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": USER_AGENT}
TIMEOUT_SEGUNDOS = 30

PASTA            = Path(__file__).resolve().parent          # conab/
PASTA_RAW        = PASTA / "raw"                            # conab/raw/
ARQUIVO_XLSX     = PASTA_RAW / "conab_atual.xlsx"
ARQUIVO_REGISTRO = PASTA_RAW / "ultimo_baixado.txt"


# ----------------------------------------------------------------------
# Rede
# ----------------------------------------------------------------------

def fetch_html(url: str) -> str:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT_SEGUNDOS)
        resp.raise_for_status()
        return resp.text
    except requests.exceptions.Timeout:
        raise RuntimeError(f"Timeout ao acessar {url}")
    except requests.exceptions.HTTPError as e:
        raise RuntimeError(f"Erro HTTP {e.response.status_code} ao acessar {url}")
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Erro de rede ao acessar {url}: {e}")


def baixar_arquivo(url: str, destino: Path) -> int:
    destino.parent.mkdir(parents=True, exist_ok=True)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT_SEGUNDOS, stream=True)
        resp.raise_for_status()
        with open(destino, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        return destino.stat().st_size
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Erro ao baixar {url}: {e}")


# ----------------------------------------------------------------------
# Identificação do boletim
# ----------------------------------------------------------------------

def encontrar_link_boletim_mais_recente(html_listagem: str) -> str:
    soup = BeautifulSoup(html_listagem, "html.parser")
    BASE_PATH = "safras/safra-de-graos/boletim-da-safra-de-graos/"
    candidatos = []
    for a in soup.find_all("a", href=True):
        href_abs = urljoin(URL_LISTAGEM, a["href"])
        if BASE_PATH in href_abs and href_abs.rstrip("/") != URL_LISTAGEM.rstrip("/"):
            candidatos.append(href_abs)
    if not candidatos:
        raise RuntimeError(
            "Nenhum link de boletim encontrado na página de listagem. "
            "Estrutura do site da CONAB pode ter mudado — revisar este script."
        )
    return candidatos[0]


def encontrar_link_xlsx_no_boletim(html_boletim: str, base_url: str) -> str:
    soup = BeautifulSoup(html_boletim, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().endswith(".xlsx") or "xlsx" in href.lower():
            if "previsao" in href.lower() or "safra" in href.lower() or "graos" in href.lower():
                return urljoin(base_url, href)
    for a in soup.find_all("a", href=True):
        if a["href"].lower().endswith(".xlsx"):
            return urljoin(base_url, a["href"])
    raise RuntimeError(
        "Nenhum link XLSX encontrado na página do boletim. "
        f"URL inspecionada: {base_url}"
    )


def nome_arquivo_da_url(url: str) -> str:
    return Path(urlparse(url).path).name


# ----------------------------------------------------------------------
# Controle de versão local
# ----------------------------------------------------------------------

def ja_temos_este_arquivo(nome_remoto: str) -> bool:
    if not ARQUIVO_REGISTRO.exists():
        return False
    return ARQUIVO_REGISTRO.read_text(encoding="utf-8").strip() == nome_remoto


def registrar_ultimo_baixado(nome: str) -> None:
    PASTA_RAW.mkdir(parents=True, exist_ok=True)
    ARQUIVO_REGISTRO.write_text(nome, encoding="utf-8")


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main() -> int:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] Iniciando verificação de boletim CONAB")

    try:
        print(f"  -> Acessando listagem: {URL_LISTAGEM}")
        html_listagem = fetch_html(URL_LISTAGEM)
    except RuntimeError as e:
        print(f"FALHA: {e}")
        return 1

    try:
        url_boletim = encontrar_link_boletim_mais_recente(html_listagem)
        print(f"  -> Boletim mais recente: {url_boletim}")
    except RuntimeError as e:
        print(f"FALHA: {e}")
        return 2

    try:
        html_boletim = fetch_html(url_boletim)
        url_xlsx = encontrar_link_xlsx_no_boletim(html_boletim, url_boletim)
        nome_xlsx = nome_arquivo_da_url(url_xlsx)
        print(f"  -> Arquivo encontrado: {nome_xlsx}")
        print(f"     URL completa: {url_xlsx}")
    except RuntimeError as e:
        print(f"FALHA: {e}")
        return 3

    if ja_temos_este_arquivo(nome_xlsx):
        print(f"  -> Já temos esta versão. Nenhuma atualização necessária.")
        return 0

    print(f"  -> Versão nova detectada. Iniciando download...")
    try:
        if ARQUIVO_XLSX.exists():
            ARQUIVO_XLSX.unlink()
            print(f"  -> XLSX anterior removido.")

        tamanho = baixar_arquivo(url_xlsx, ARQUIVO_XLSX)
        print(f"  -> Salvo em: {ARQUIVO_XLSX} ({tamanho / 1024:.1f} KB)")

        registrar_ultimo_baixado(nome_xlsx)
        print(f"  -> Registro atualizado: {nome_xlsx}")
    except RuntimeError as e:
        print(f"FALHA: {e}")
        return 4

    # Dispara ETL
    etl_script = PASTA / "etl_conab.py"
    if etl_script.exists():
        print(f"\n  -> Gerando CSV...")
        result = subprocess.run([sys.executable, str(etl_script)])
        if result.returncode != 0:
            print(
                "\nAVISO: etl_conab.py encerrou com erro — "
                "o CSV atual foi preservado."
            )
    else:
        print(f"  -> etl_conab.py não encontrado em {PASTA}, pulando geração de CSV.")

    print(f"\n[OK] Boletim atualizado com sucesso.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
