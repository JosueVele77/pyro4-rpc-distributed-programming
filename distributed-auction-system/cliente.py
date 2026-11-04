from threading import Event, Thread
import Pyro4


def mostrar_estado(estado):
    postor = estado["mejor_postor"] or "Sin ofertas"
    print(
        f"\nProducto: {estado['producto']} | Precio: ${estado['precio_actual']:.2f}"
        f" | Mejor postor: {postor} | Tiempo: {estado['tiempo_restante']:.1f} s",
        flush=True,
    )
    if estado["finalizada"]:
        print("Subasta finalizada. Presiona Enter para salir.", flush=True)


def consultar_cambios(uri, nombre, estado_anterior, detener):
    try:
        # Cada hilo utiliza su propia conexión de Pyro4.
        with Pyro4.Proxy(uri) as subasta:
            subasta._pyroTimeout = 3
            while not detener.wait(1):
                estado = subasta.consultar_estado(nombre)
                if (
                    estado["precio_actual"] != estado_anterior["precio_actual"]
                    or estado["finalizada"] != estado_anterior["finalizada"]
                ):
                    mostrar_estado(estado)
                estado_anterior = estado
                if estado["finalizada"]:
                    detener.set()
    except (Pyro4.errors.CommunicationError, Pyro4.errors.NamingError):
        print("\nSe perdió la conexión con el servidor. Presiona Enter para salir.", flush=True)
        detener.set()


def main():
    detener = Event()
    hilo = None
    try:
        nombre = input("Ingresa tu nombre: ").strip()
        # Consultar el Name Server indicado sin buscar otros equipos por broadcast.
        direccion = f"PYRONAME:subastas.central@{Pyro4.config.NS_HOST}:{Pyro4.config.NS_PORT}"
        with Pyro4.Proxy(direccion) as subasta:
            subasta._pyroTimeout = 3
            subasta._pyroBind()
            estado = subasta.registrar_cliente(nombre)
            mostrar_estado(estado)
            if estado["finalizada"]:
                return

            hilo = Thread(
                target=consultar_cambios,
                args=(str(subasta._pyroUri), nombre, estado, detener),
                daemon=True,
            )
            hilo.start()
            while not detener.is_set():
                entrada = input("\nIngresa una oferta o escribe 'salir': ").strip()
                if entrada.lower() == "salir" or detener.is_set():
                    break
                try:
                    monto = float(entrada)
                    estado = subasta.ofertar(nombre, monto)
                    print(f"Oferta aceptada. Precio actual: ${estado['precio_actual']:.2f}")
                except (ValueError, RuntimeError) as error:
                    print(f"Oferta rechazada: {error}")
    except ValueError as error:
        print(error)
    except (Pyro4.errors.CommunicationError, Pyro4.errors.NamingError) as error:
        print("No se pudo conectar. Mantén abiertos el servidor de nombres y servidor.py.")
        print(f"Detalle: {error}")
    except (EOFError, KeyboardInterrupt):
        print("\nCliente cerrado.")
    finally:
        detener.set()
        if hilo is not None:
            hilo.join(timeout=4)


if __name__ == "__main__":
    main()
