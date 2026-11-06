from math import isfinite
from threading import Event, Lock, Thread
from time import monotonic

import Pyro4
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout

from consola import mostrar_estado


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
            "clientes": list(self.clientes),
            "finalizada": self.fase == "finalizada",
        }

    # Los métodos privados no se exponen por Pyro4: solo los usa el operador local.
    def _preparar_subasta(self, producto, precio_base, duracion):
        if not isinstance(producto, str) or not producto.strip():
            raise ValueError("Ingresa el nombre del producto.")
        precio_base = validar_numero_positivo(precio_base, "El precio base")
        duracion = validar_numero_positivo(duracion, "La duración")
        with self.bloqueo:
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

    def _iniciar_subasta(self):
        with self.bloqueo:
            if self.fase != "preparada":
                raise RuntimeError("Primero prepara un producto para subastar.")
            # Solo el operador del servidor decide cuándo comienza el plazo.
            self.fin = monotonic() + self.duracion
            self.fase = "en_curso"
            self.version += 1
            return self._obtener_estado()

    def _consultar_sala(self):
        with self.bloqueo:
            return self._obtener_estado()

    def salir_cliente(self, nombre):
        with self.bloqueo:
            self._validar_cliente(nombre)
            self.clientes.remove(nombre)
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


def notificar_cambios(subasta, detener):
    version = -1
    while not detener.wait(0.25):
        estado = subasta._consultar_sala()
        if estado["version"] != version:
            mostrar_estado(estado)
            version = estado["version"]


def administrar_subastas(subasta):
    sesion = PromptSession()
    detener = Event()
    hilo = Thread(target=notificar_cambios, args=(subasta, detener), daemon=True)
    hilo.start()
    print("Comandos del servidor: preparar, iniciar, estado, ayuda, salir.")
    try:
        while True:
            comando = sesion.prompt("Servidor > ").strip().lower()
            if comando == "salir":
                break
            try:
                if comando == "preparar":
                    producto = sesion.prompt("Producto a subastar: ").strip()
                    precio = float(sesion.prompt("Precio base: "))
                    duracion = float(sesion.prompt("Duración en segundos: "))
                    subasta._preparar_subasta(producto, precio, duracion)
                    print("Producto preparado. Escribe 'iniciar' cuando estén listos.")
                elif comando == "iniciar":
                    subasta._iniciar_subasta()
                elif comando == "estado":
                    mostrar_estado(subasta._consultar_sala())
                elif comando == "ayuda":
                    print("preparar: ingresar producto, precio base y duración en segundos.")
                    print("iniciar: comenzar la subasta preparada. estado: consultar la sala.")
                    print("salir: cerrar el servidor. Los clientes solo pueden ofertar y salir.")
                elif comando:
                    print("Comando inválido. Escribe 'ayuda'.")
            except (ValueError, RuntimeError) as error:
                print(f"No se pudo realizar la operación: {error}")
    finally:
        detener.set()
        hilo.join(timeout=1)


def main():
    with patch_stdout():
        try:
            with Pyro4.Daemon() as servidor, Pyro4.locateNS(
                host=Pyro4.config.NS_HOST, port=Pyro4.config.NS_PORT
            ) as registro:
                subasta = Subasta()
                uri = servidor.register(subasta)
                registro.register("subastas.central", uri)
                print(f"Dirección del servicio: {uri}")
                print("Sala de espera lista. Configura los productos desde esta consola.")
                # Atender clientes mientras el operador utiliza la consola local.
                hilo = Thread(target=servidor.requestLoop, daemon=True)
                hilo.start()
                try:
                    administrar_subastas(subasta)
                finally:
                    servidor.shutdown()
                    hilo.join(timeout=3)
                    try:
                        # Renovar la conexión si estuvo inactiva durante las subastas.
                        registro._pyroRelease()
                        if registro.lookup("subastas.central") == uri:
                            registro.remove("subastas.central")
                    except Pyro4.errors.PyroError:
                        pass
        except (Pyro4.errors.NamingError, Pyro4.errors.CommunicationError) as error:
            print("No se pudo conectar al servidor de nombres. Ejecuta: python -m Pyro4.naming")
            print(f"Detalle: {error}")
        except (EOFError, KeyboardInterrupt):
            print("\nServidor cerrado.")

if __name__ == "__main__":
    main()
