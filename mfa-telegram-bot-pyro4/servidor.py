from getpass import getpass

import Pyro4

from autenticacion import ServicioAutenticacion, Usuario
from configuracion import obtener_token
from telegram_bot import BotTelegram


def registrar_usuarios():
    usuarios = {}
    print("Registra las cuentas y sus chats privados. Deja el usuario vacío para iniciar.")
    while True:
        nombre = input("Usuario: ").strip()
        if not nombre:
            if usuarios:
                return usuarios
            print("Debes registrar al menos un usuario.")
            continue
        if nombre in usuarios:
            print("Ese usuario ya fue registrado.")
            continue
        password = getpass("Contraseña: ")
        chat_id = input("chat_id de Telegram: ").strip()
        try:
            usuarios[nombre] = Usuario.crear(password, chat_id)
            print("Usuario registrado.")
        except ValueError as error:
            print(error)


def main():
    try:
        with Pyro4.Daemon() as servidor, Pyro4.locateNS(
            host=Pyro4.config.NS_HOST, port=Pyro4.config.NS_PORT
        ) as registro:
            token = obtener_token()
            telegram = BotTelegram(token)
            usuarios = registrar_usuarios()
            servicio = ServicioAutenticacion(usuarios, telegram)
            uri = servidor.register(servicio)
            registro.register("autenticacion.mfa", uri)
            print(f"Servidor MFA listo: autenticacion.mfa ({uri}).")
            try:
                servidor.requestLoop()
            finally:
                try:
                    registro._pyroRelease()
                    if registro.lookup("autenticacion.mfa") == uri:
                        registro.remove("autenticacion.mfa")
                except Pyro4.errors.PyroError:
                    pass
    except (Pyro4.errors.NamingError, Pyro4.errors.CommunicationError):
        print("No se pudo conectar al Name Server. Ejecuta primero: python -m Pyro4.naming")
    except ValueError as error:
        print(error)
    except (EOFError, KeyboardInterrupt):
        print("\nServidor cerrado.")


if __name__ == "__main__":
    main()
