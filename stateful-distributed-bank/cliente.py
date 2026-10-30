import Pyro4
from excepciones import SaldoInsuficiente

def main():
    # Reutilizar la conexión mantiene el saldo entre operaciones.
    try:
        with Pyro4.Proxy("PYRONAME:cuenta_bancaria") as cuenta:
            # Comprobar la conexión antes de mostrar el menú.
            cuenta._pyroBind()
            while True:
                print("\n--- Cuenta bancaria ---")
                print("1. Depositar")
                print("2. Retirar")
                print("3. Consultar saldo")
                print("4. Salir")
                opcion = input("Selecciona una opción: ").strip()

                if opcion == "4":
                    break
                if opcion not in ("1", "2", "3"):
                    print("Opción inválida.")
                    continue

                try:
                    if opcion == "3":
                        saldo = cuenta.consultar_saldo()
                    else:
                        monto = float(input("Ingresa el monto: "))
                        if opcion == "1":
                            saldo = cuenta.depositar(monto)
                        else:
                            saldo = cuenta.retirar(monto)

                    print(f"Saldo actual: ${saldo:.2f}")
                except SaldoInsuficiente as error:
                    print(error)
                except ValueError:
                    print("Ingresa un monto numérico, positivo y finito.")
    except (Pyro4.errors.CommunicationError, Pyro4.errors.NamingError):
        print("No se pudo conectar con el servicio bancario o se perdió la conexión.")
        print("Mantén abiertos el servidor de nombres y servidor.py.")
        print("Después vuelve a ejecutar cliente.py para iniciar una nueva sesión.")


if __name__ == "__main__":
    main()
