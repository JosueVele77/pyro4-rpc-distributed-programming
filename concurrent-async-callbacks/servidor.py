import Pyro4
import time

@Pyro4.expose
class ProcesadorArchivos:
    def procesar_datos_pesados(self, datos):
        print(f"Iniciando procesamiento de: {datos}...")
        time.sleep(5)  # Simula una tarea intensiva que bloquea el hilo por 5 segundos
        print("Procesamiento terminado.")
        return f"Resultado exitoso para: {datos}"

if __name__ == "__main__":
    daemon = Pyro4.Daemon()
    ns = Pyro4.locateNS()
    uri = daemon.register(ProcesadorArchivos)
    ns.register("practica.procesador", uri)
    print("Servidor de procesamiento asíncrono activo.")
    daemon.requestLoop()