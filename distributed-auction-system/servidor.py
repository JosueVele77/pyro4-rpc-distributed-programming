from math import isfinite
from threading import Lock
from time import monotonic
import Pyro4

def validar_numero_positivo(valor, nombre):
    if type(valor) not in (int, float):
        raise ValueError(f"{nombre} debe ser un número positivo y finito.")
    try:
        numero = float(valor)
    except OverflowError:
        raise ValueError(f"{nombre} es demasiado grande.") from None
    if not isfinite(numero) or numero <= 0:
        raise ValueError(f"{nombre} debe ser un número positivo y finito.")
    return numero


@Pyro4.expose
class Subasta:
    def __init__(self, producto, precio_base, duracion):
        self.producto = producto
        self.precio_actual = validar_numero_positivo(precio_base, "El precio base")
        duracion = validar_numero_positivo(duracion, "La duración")
        self.fin = monotonic() + duracion
        self.mejor_postor = None
        self.clientes = set()
        self.bloqueo = Lock()

    def registrar_cliente(self, nombre):
        if not isinstance(nombre, str) or not nombre.strip():
            raise ValueError("El nombre del cliente no puede estar vacío.")
        with self.bloqueo:
            self.clientes.add(nombre)
            return self._obtener_estado()

    def _validar_cliente(self, nombre):
        if not isinstance(nombre, str) or nombre not in self.clientes:
            raise ValueError("El cliente debe registrarse antes de participar.")

    def _obtener_estado(self):
        # Se consulta siempre dentro del bloqueo para devolver datos coherentes.
        tiempo_restante = max(0.0, self.fin - monotonic())
        return {
            "producto": self.producto,
            "precio_actual": self.precio_actual,
            "mejor_postor": self.mejor_postor,
            "tiempo_restante": tiempo_restante,
            "finalizada": tiempo_restante == 0,
        }

    def consultar_estado(self, nombre):
        with self.bloqueo:
            self._validar_cliente(nombre)
            return self._obtener_estado()

    def ofertar(self, nombre, monto):
        monto = validar_numero_positivo(monto, "El monto")
        # Validar y actualizar bajo el mismo bloqueo evita ofertas en carrera.
        with self.bloqueo:
            self._validar_cliente(nombre)
            if monotonic() >= self.fin:
                raise RuntimeError("La subasta ha finalizado. No se aceptan más ofertas.")
            if monto <= self.precio_actual:
                raise ValueError(
                    f"La oferta debe superar el precio actual de ${self.precio_actual:.2f}."
                )
            self.precio_actual = monto
            self.mejor_postor = nombre
            return self._obtener_estado()


def main():
    try:
        with Pyro4.Daemon() as servidor, Pyro4.locateNS(
            host=Pyro4.config.NS_HOST, port=Pyro4.config.NS_PORT
        ) as registro:
            # Una sola instancia comparte el estado entre todos los clientes.
            subasta = Subasta("Computadora portátil", precio_base=100, duracion=100)
            uri = servidor.register(subasta)
            registro.register("subastas.central", uri)
            print(f"Dirección del servicio: {uri}", flush=True)
            print("Servidor listo: subastas.central. Duración: 100 segundos.", flush=True)
            servidor.requestLoop()
    except (Pyro4.errors.NamingError, Pyro4.errors.CommunicationError) as error:
        print("No se pudo conectar al servidor de nombres. Ejecuta: python -m Pyro4.naming")
        print(f"Detalle: {error}")

if __name__ == "__main__":
    main()
