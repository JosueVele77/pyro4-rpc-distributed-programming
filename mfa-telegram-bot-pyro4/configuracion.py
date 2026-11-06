from getpass import getpass
import os
from pathlib import Path


def obtener_token():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        archivo = Path(__file__).with_name(".telegram_token")
        if archivo.is_file():
            token = archivo.read_text(encoding="utf-8").strip()
    return token or getpass("Token del bot de Telegram: ").strip()
