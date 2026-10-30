import Pyro4

# El cliente ya no necesita la URI larga, solo el nombre lógico registrado
mensajeria = Pyro4.Proxy("PYRONAME:practica.mensajeria")

respuesta = mensajeria.enviar_mensaje("Chris", "Hola desde el cliente RPC!")
print("Respuesta del servidor:", respuesta)