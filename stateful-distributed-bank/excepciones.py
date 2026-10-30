from Pyro4.util import SerializerBase

class SaldoInsuficiente(Exception):
    """El monto solicitado supera el saldo de la cuenta."""

# Permite recibir la excepción personalizada en el cliente remoto.
SerializerBase.register_dict_to_class(
    "excepciones.SaldoInsuficiente",
    lambda nombre_clase, datos: SaldoInsuficiente(*datos["args"]),
)
