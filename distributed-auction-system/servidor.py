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
    def __init__(self):
        self.producto = ""
        self.precio_actual = 0.0
        self.duracion = 0.0
        self.fin = None
        self.mejor_postor = None
        self.clientes = []
        self.anfitrion = None
        self.fase = "espera"
        self.numero_subasta = 0
        self.version = 0
        self.bloqueo = Lock()

    def registrar_cliente(self, nombre):
        if not isinstance(nombre, str) or not nombre.strip():
            raise ValueError("El nombre del cliente no puede estar vacío.")
        nombre = nombre.strip()
        with self.bloqueo:
            if nombre in self.clientes:
                raise ValueError("Ese nombre ya está conectado. Utiliza otro nombre.")
            self.clientes.append(nombre)
            if self.anfitrion is None:
                self.anfitrion = nombre
            self.version += 1
            return self._obtener_estado()

    def _validar_cliente(self, nombre):
        if not isinstance(nombre, str) or nombre not in self.clientes:
            raise ValueError("El cliente debe registrarse antes de participar.")

    def _obtener_estado(self):
        # Se consulta siempre dentro del bloqueo para devolver datos coherentes.
        tiempo_restante = 0.0 if self.fin is None else max(0.0, self.fin - monotonic())
        if self.fase == "en_curso" and tiempo_restante == 0:
            self.fase = "finalizada"
            self.version += 1
        return {
            "fase": self.fase,
            "numero_subasta": self.numero_subasta,
            "version": self.version,
            "producto": self.producto,
            "precio_actual": self.precio_actual,
            "mejor_postor": self.mejor_postor,
            "tiempo_restante": tiempo_restante,
            "duracion": self.duracion,
            "anfitrion": self.anfitrion,
            "clientes": list(self.clientes),
            "finalizada": self.fase == "finalizada",
        }

    def _validar_anfitrion(self, nombre):
        self._validar_cliente(nombre)
        if nombre != self.anfitrion:
            raise ValueError("Solo el anfitrión puede preparar e iniciar una subasta.")

    def preparar_subasta(self, nombre, producto, precio_base, duracion):
        if not isinstance(producto, str) or not producto.strip():
            raise ValueError("Ingresa el nombre del producto.")
        precio_base = validar_numero_positivo(precio_base, "El precio base")
        duracion = validar_numero_positivo(duracion, "La duración")
        with self.bloqueo:
            self._validar_anfitrion(nombre)
            self._obtener_estado()
            if self.fase == "en_curso":
                raise RuntimeError("Espera a que termine la subasta actual.")
            self.producto = producto.strip()
            self.precio_actual = precio_base
            self.duracion = duracion
            self.fin = None
            self.mejor_postor = None
            self.fase = "preparada"
            self.numero_subasta += 1
            self.version += 1
            return self._obtener_estado()

    def iniciar_subasta(self, nombre):
        with self.bloqueo:
            self._validar_anfitrion(nombre)
            if self.fase != "preparada":
                raise RuntimeError("Primero prepara un producto para subastar.")
            # El plazo empieza al iniciar, después de que entren los participantes.
            self.fin = monotonic() + self.duracion
            self.fase = "en_curso"
            self.version += 1
            return self._obtener_estado()

    def salir_cliente(self, nombre):
        with self.bloqueo:
            self._validar_cliente(nombre)
            self.clientes.remove(nombre)
            if nombre == self.anfitrion:
                self.anfitrion = self.clientes[0] if self.clientes else None
            self.version += 1
            return self._obtener_estado()

    def consultar_estado(self, nombre):
        with self.bloqueo:
            self._validar_cliente(nombre)
            return self._obtener_estado()

    def ofertar(self, nombre, monto, numero_subasta):
        monto = validar_numero_positivo(monto, "El monto")
        # Validar y actualizar bajo el mismo bloqueo evita ofertas en carrera.
        with self.bloqueo:
            self._validar_cliente(nombre)
            self._obtener_estado()
            if type(numero_subasta) is not int or numero_subasta != self.numero_subasta:
                raise ValueError("El producto cambió. Revisa la subasta y vuelve a ofertar.")
            if self.fase != "en_curso":
                raise RuntimeError("No hay una subasta en curso. Espera al inicio.")
            if monto <= self.precio_actual:
                raise ValueError(
                    f"La oferta debe superar el precio actual de ${self.precio_actual:.2f}."
                )
            self.precio_actual = monto
            self.mejor_postor = nombre
            self.version += 1
            return self._obtener_estado()


def main():
    try:
        with Pyro4.Daemon() as servidor, Pyro4.locateNS(
            host=Pyro4.config.NS_HOST, port=Pyro4.config.NS_PORT
        ) as registro:
            # Una sola instancia comparte el estado entre todos los clientes.
            subasta = Subasta()
            uri = servidor.register(subasta)
            registro.register("subastas.central", uri)
            print(f"Dirección del servicio: {uri}", flush=True)
            print("Sala de espera lista: subastas.central. El primer cliente será el anfitrión.", flush=True)
            servidor.requestLoop()
    except (Pyro4.errors.NamingError, Pyro4.errors.CommunicationError) as error:
        print("No se pudo conectar al servidor de nombres. Ejecuta: python -m Pyro4.naming")
        print(f"Detalle: {error}")

if __name__ == "__main__":
    main()
