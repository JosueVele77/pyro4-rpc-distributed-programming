from getpass import getpass

import Pyro4

from excepciones import CodigoIncorrecto, ErrorAutenticacion


def main():
    direccion = f"PYRONAME:autenticacion.mfa@{Pyro4.config.NS_HOST}:{Pyro4.config.NS_PORT}"
    try:
        usuario = input("Usuario: ").strip()
        password = getpass("Contraseña: ")
        # Mantener este proxy vincula ambos factores a la misma conexión.
        with Pyro4.Proxy(direccion) as servicio:
            servicio._pyroTimeout = 20
            print(servicio.iniciar_sesion(usuario, password))
            while True:
                codigo = input("Código de Telegram (o 'salir'): ").strip()
                if codigo.lower() == "salir":
                    return
                try:
                    if servicio.verificar_codigo_mfa(usuario, codigo):
                        print("Acceso autorizado. Autenticación multifactor completada.")
                        return
                except CodigoIncorrecto as error:
                    print(error)
    except ErrorAutenticacion as error:
        print(error)
    except Pyro4.errors.PyroError:
        print("No se pudo conectar. Mantén abiertos el Name Server y servidor.py.")
    except (EOFError, KeyboardInterrupt):
        print("\nInicio de sesión cancelado.")


if __name__ == "__main__":
    main()
