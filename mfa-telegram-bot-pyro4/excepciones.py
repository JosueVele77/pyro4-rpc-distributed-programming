from Pyro4.util import SerializerBase


class ErrorAutenticacion(Exception):
    """Error controlado del proceso de autenticación."""


class CredencialesInvalidas(ErrorAutenticacion):
    """El usuario o la contraseña no son válidos."""


class CodigoExpirado(ErrorAutenticacion):
    """El código superó su tiempo de validez."""


class CodigoIncorrecto(ErrorAutenticacion):
    """El código es incorrecto o no pertenece a esta conexión."""


class CuentaBloqueada(ErrorAutenticacion):
    """La cuenta alcanzó el límite de intentos fallidos."""


class ErrorTelegram(ErrorAutenticacion):
    """Telegram no pudo confirmar la operación."""


# Registrar únicamente las excepciones conocidas para recibirlas por Pyro4.
for tipo in (
    ErrorAutenticacion,
    CredencialesInvalidas,
    CodigoExpirado,
    CodigoIncorrecto,
    CuentaBloqueada,
    ErrorTelegram,
):
    SerializerBase.register_dict_to_class(
        f"{tipo.__module__}.{tipo.__name__}",
        lambda nombre, datos, clase=tipo: clase(*datos["args"]),
    )
