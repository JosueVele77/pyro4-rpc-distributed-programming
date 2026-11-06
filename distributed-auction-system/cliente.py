from threading import Event, Lock, Thread

import Pyro4
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout

from consola import mostrar_estado


class ClienteSubasta:
    def __init__(self, nombre, subasta, sesion, estado):
        self.nombre = nombre
        self.subasta = subasta
        self.sesion = sesion
        self.estado = estado
        self.bloqueo = Lock()
        self.detener = Event()
        self.numero_entrada = estado["numero_subasta"]
        self.escribiendo = False

    def capturar_subasta(self, entrada):
        if not entrada.text:
            self.escribiendo = False
        elif not self.escribiendo:
            # Asociar el monto al producto visible al comenzar a escribir.
            with self.bloqueo:
                self.numero_entrada = self.estado["numero_subasta"]
            self.escribiendo = True

    def actualizar_estado(self, estado):
        with self.bloqueo:
            anterior = self.estado
            # Una consulta antigua no debe sobrescribir una oferta más reciente.
            if estado["version"] < anterior["version"]:
                return
            self.estado = estado
            if estado["version"] == anterior["version"]:
                return
            solo_oferta_propia = (
                estado["precio_actual"] != anterior["precio_actual"]
                and estado["mejor_postor"] == self.nombre
                and all(
                    estado[campo] == anterior[campo]
                    for campo in ("fase", "numero_subasta", "clientes")
                )
            )
            if not solo_oferta_propia:
                mostrar_estado(estado)

    def consultar_cambios(self):
        try:
            # El hilo de consultas utiliza su propia conexión al mismo servidor.
            with Pyro4.Proxy(str(self.subasta._pyroUri)) as consulta:
                consulta._pyroTimeout = 2
                while not self.detener.wait(0.25):
                    self.actualizar_estado(consulta.consultar_estado(self.nombre))
        except (Pyro4.errors.PyroError, ValueError) as error:
            print(f"\nSe perdió la conexión con la sala: {error}")
            print("Presiona Enter para salir.")
            self.detener.set()

    def ejecutar(self):
        mostrar_estado(self.estado)
        print("El servidor configura e inicia las subastas.")
        print("Escribe un monto para ofertar. Comandos: estado, ayuda, salir.")
        hilo = Thread(target=self.consultar_cambios, daemon=True)
        self.sesion.default_buffer.on_text_changed += self.capturar_subasta
        hilo.start()
        try:
            while not self.detener.is_set():
                entrada = self.sesion.prompt("Ingrese su oferta o escriba 'salir' para terminar: ").strip()
                if entrada.lower() == "salir" or self.detener.is_set():
                    break
                if not entrada:
                    continue
                try:
                    self.procesar_entrada(entrada, self.numero_entrada)
                except (ValueError, RuntimeError) as error:
                    print(f"No se pudo realizar la operación: {error}")
        finally:
            self.detener.set()
            hilo.join(timeout=3)
            self.sesion.default_buffer.on_text_changed -= self.capturar_subasta

    def procesar_entrada(self, entrada, numero_subasta):
        comando = entrada.lower()
        if comando == "estado":
            estado = self.subasta.consultar_estado(self.nombre)
            with self.bloqueo:
                if estado["version"] >= self.estado["version"]:
                    self.estado = estado
                mostrar_estado(self.estado)
        elif comando == "ayuda":
            print("El servidor decide el producto, el precio base y el tiempo.")
            print("estado: consultar la sala. salir: desconectarte sin detener el servidor.")
            print("Para ofertar escribe un número mayor al precio actual, por ejemplo: 150.")
        elif comando in ("preparar", "iniciar"):
            raise ValueError("Solo el operador del servidor puede configurar e iniciar subastas.")
        else:
            try:
                monto = float(entrada)
            except ValueError:
                raise ValueError("Escribe un monto numérico o un comando; usa 'ayuda'.") from None
            estado = self.subasta.ofertar(self.nombre, monto, numero_subasta)
            self.actualizar_estado(estado)
            print(f"Oferta aceptada: ${monto:.2f}.")


def main():
    direccion = f"PYRONAME:subastas.central@{Pyro4.config.NS_HOST}:{Pyro4.config.NS_PORT}"
    with patch_stdout():
        try:
            sesion = PromptSession()
            nombre = sesion.prompt("Ingresa tu nombre: ").strip()
            with Pyro4.Proxy(direccion) as subasta:
                subasta._pyroTimeout = 2
                subasta._pyroBind()
                estado = subasta.registrar_cliente(nombre)
                try:
                    ClienteSubasta(nombre, subasta, sesion, estado).ejecutar()
                finally:
                    # Dar de baja al participante también al cerrar con Ctrl+C.
                    try:
                        subasta.salir_cliente(nombre)
                        print("Saliste de la sala. Conexión cerrada.")
                    except (Pyro4.errors.PyroError, ValueError):
                        print("Conexión cerrada; el servidor ya no está disponible.")
        except (ValueError, RuntimeError) as error:
            print(error)
        except Pyro4.errors.PyroError as error:
            print(f"No se pudo conectar al servidor de subastas. Detalle: {error}")
        except (EOFError, KeyboardInterrupt):
            print("\nCliente cerrado.")


if __name__ == "__main__":
    main()
