import os
import socket
import subprocess
import sys

from shortsgen.config import settings

N8N_PORT = 5678
HTTP_SERVE_PORT = 8901

_NEW_CONSOLE = subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0


def _port_open(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def ensure_n8n_running() -> bool:
    """Sobe o n8n numa janela propria (com os env vars que ele precisa nesta
    maquina) se a porta ainda nao estiver em uso. Retorna True se subiu agora."""
    if _port_open(N8N_PORT):
        return False
    env = {**os.environ, "NODES_EXCLUDE": "[]", "PYTHONUTF8": "1"}
    subprocess.Popen("npx n8n", env=env, shell=True, creationflags=_NEW_CONSOLE)
    return True


def ensure_http_server_running() -> bool:
    """Sobe um servidor HTTP simples servindo `output_dir`, usado pelo n8n pra
    ler os clipes (workaround pro node de arquivo nativo, ver CHANGELOG)."""
    if _port_open(HTTP_SERVE_PORT):
        return False
    subprocess.Popen(
        [sys.executable, "-m", "http.server", str(HTTP_SERVE_PORT), "--directory", str(settings.output_dir), "--bind", "127.0.0.1"],
        creationflags=_NEW_CONSOLE,
    )
    return True
