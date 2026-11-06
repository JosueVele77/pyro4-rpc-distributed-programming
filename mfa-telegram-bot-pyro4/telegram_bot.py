import json
from urllib.error import URLError
from urllib.request import Request, urlopen

from excepciones import ErrorTelegram
from configuracion import obtener_token


class BotTelegram:
    def __init__(self, token):
        if not isinstance(token, str) or not token.strip():
            raise ValueError("Debes configurar el token del bot de Telegram.")
        self._token = token.strip()

    def _solicitar(self, metodo, datos):
        direccion = f"https://api.telegram.org/bot{self._token}/{metodo}"
        peticion = Request(
            direccion,
            data=json.dumps(datos).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(peticion, timeout=10) as respuesta:
                resultado = json.load(respuesta)
        except (URLError, OSError, ValueError):
            # No propagar errores HTTP que podrían incluir el token en la URL.
            raise ErrorTelegram("No se pudo comunicar con Telegram. Revisa el token y la conexión.") from None
        if not isinstance(resultado, dict) or resultado.get("ok") is not True or "result" not in resultado:
            raise ErrorTelegram("Telegram rechazó la operación. Revisa el token y el chat_id.")
        return resultado.get("result")

    def enviar_codigo(self, chat_id, codigo, validez):
        self._solicitar(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": f"Tu código MFA es: {codigo}\nVálido durante {validez:g} segundos. No lo compartas.",
            },
        )

    def consultar_chat_ids(self):
        actualizaciones = self._solicitar("getUpdates", {"allowed_updates": ["message"]})
        return sorted({
            evento["message"]["chat"]["id"]
            for evento in actualizaciones
            if evento.get("message", {}).get("chat", {}).get("type") == "private"
        })


def main():
    try:
        token = obtener_token()
        identificadores = BotTelegram(token).consultar_chat_ids()
        if not identificadores:
            print("Abre tu bot en Telegram, envía /start y vuelve a ejecutar esta utilidad.")
        for chat_id in identificadores:
            print(f"chat_id de chat privado: {chat_id}")
    except (ErrorTelegram, ValueError) as error:
        print(error)
    except (EOFError, KeyboardInterrupt):
        print("\nConsulta cancelada.")


if __name__ == "__main__":
    main()
