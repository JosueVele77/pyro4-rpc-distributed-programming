import Pyro4


@Pyro4.expose
class ServicioMensajes:
    def enviar_mensaje(self, remitente, mensaje):
        print(f"[{remitente}]: {mensaje}")
        return "Mensaje recibido por el servidor."


if __name__ == "__main__":
    daemon = Pyro4.Daemon()
    ns = Pyro4.locateNS()  # Localiza el Name Server automáticamente
    uri = daemon.register(ServicioMensajes)

    # Registra la URI dinámica bajo un nombre estático fácil de recordar
    ns.register("practica.mensajeria", uri)

    print("Servicio de mensajería registrado en el Name Server.")
    daemon.requestLoop()