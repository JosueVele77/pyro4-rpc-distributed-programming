from dataclasses import dataclass, field
from hashlib import pbkdf2_hmac, sha256
from math import ceil
import secrets
from threading import Lock
from time import monotonic

import Pyro4

from excepciones import (
    CodigoExpirado,
    CodigoIncorrecto,
    CuentaBloqueada,
    CredencialesInvalidas,
)

ITERACIONES_PASSWORD = 600_000


@dataclass(frozen=True)
class Usuario:
    sal: bytes
    resumen_password: bytes
    chat_id: str

    @classmethod
    def crear(cls, password, chat_id):
        if not isinstance(password, str) or not password or len(password) > 1024:
            raise ValueError("La contraseña debe tener entre 1 y 1024 caracteres.")
        if not str(chat_id).isascii() or not str(chat_id).isdigit() or int(chat_id) <= 0:
            raise ValueError("El chat_id debe ser el número positivo de un chat privado.")
        sal = secrets.token_bytes(16)
        resumen = pbkdf2_hmac("sha256", password.encode("utf-8"), sal, ITERACIONES_PASSWORD)
        return cls(sal, resumen, str(int(chat_id)))

    def comprobar_password(self, password):
        resumen = pbkdf2_hmac("sha256", password.encode("utf-8"), self.sal, ITERACIONES_PASSWORD)
        return secrets.compare_digest(resumen, self.resumen_password)


@dataclass
class EstadoMFA:
    resumen_codigo: bytes | None = None
    expira_en: float = 0.0
    conexion: object = None
    intentos: int = 0
    bloqueado_hasta: float = 0.0
    bloqueo: object = field(default_factory=Lock, repr=False)


@Pyro4.expose
class ServicioAutenticacion:
    def __init__(
        self, usuarios, telegram, validez=180, limite_intentos=3,
        tiempo_bloqueo=60, reloj=monotonic,
    ):
        self._usuarios = dict(usuarios)
        self._estados = {nombre: EstadoMFA() for nombre in usuarios}
        self._telegram = telegram
        self._validez = validez
        self._limite_intentos = limite_intentos
        self._tiempo_bloqueo = tiempo_bloqueo
        self._reloj = reloj

    def _obtener_usuario(self, usuario):
        if not isinstance(usuario, str) or usuario not in self._usuarios:
            raise CredencialesInvalidas("Usuario o contraseña inválidos.")
        return self._usuarios[usuario], self._estados[usuario]

    def _invalidar_codigo(self, estado):
        estado.resumen_codigo = None
        estado.expira_en = 0.0
        estado.conexion = None

    def _comprobar_bloqueo(self, estado):
        if estado.bloqueado_hasta:
            restante = estado.bloqueado_hasta - self._reloj()
            if restante > 0:
                raise CuentaBloqueada(f"Cuenta bloqueada. Intenta nuevamente en {ceil(restante)} segundos.")
            estado.bloqueado_hasta = 0.0
            estado.intentos = 0

    def _registrar_fallo(self, estado, error):
        estado.intentos += 1
        if estado.intentos >= self._limite_intentos:
            estado.bloqueado_hasta = self._reloj() + self._tiempo_bloqueo
            self._invalidar_codigo(estado)
            raise CuentaBloqueada(f"Demasiados intentos. Cuenta bloqueada durante {self._tiempo_bloqueo:g} segundos.")
        raise error

    def iniciar_sesion(self, usuario, password):
        cuenta, estado = self._obtener_usuario(usuario)
        # Un bloqueo por usuario permite atender otras cuentas durante el envío HTTP.
        with estado.bloqueo:
            self._comprobar_bloqueo(estado)
            if (
                not isinstance(password, str)
                or len(password) > 1024
                or not cuenta.comprobar_password(password)
            ):
                self._registrar_fallo(estado, CredencialesInvalidas("Usuario o contraseña inválidos."))

            self._invalidar_codigo(estado)
            codigo = f"{secrets.randbelow(1_000_000):06d}"
            # Activar el código únicamente si Telegram confirma el envío.
            self._telegram.enviar_codigo(cuenta.chat_id, codigo, self._validez)
            estado.resumen_codigo = sha256(codigo.encode("ascii")).digest()
            estado.expira_en = self._reloj() + self._validez
            estado.conexion = Pyro4.current_context.client
            return f"Código MFA enviado a tu Telegram. Válido durante {self._validez:g} segundos."

    def verificar_codigo_mfa(self, usuario, codigo):
        _, estado = self._obtener_usuario(usuario)
        with estado.bloqueo:
            self._comprobar_bloqueo(estado)
            # Exigir la misma conexión que ya comprobó el primer factor.
            if estado.resumen_codigo is None or estado.conexion is not Pyro4.current_context.client:
                raise CodigoIncorrecto("No hay un código activo para esta conexión. Inicia sesión nuevamente.")
            if self._reloj() >= estado.expira_en:
                self._invalidar_codigo(estado)
                raise CodigoExpirado("El código expiró. Inicia sesión para solicitar otro.")
            if (
                not isinstance(codigo, str)
                or len(codigo) != 6
                or not codigo.isascii()
                or not codigo.isdigit()
                or not secrets.compare_digest(sha256(codigo.encode("ascii")).digest(), estado.resumen_codigo)
            ):
                self._registrar_fallo(estado, CodigoIncorrecto("Código MFA incorrecto."))

            # Consumirlo bajo el mismo bloqueo evita reutilizarlo o validarlo dos veces.
            self._invalidar_codigo(estado)
            estado.intentos = 0
            return True
