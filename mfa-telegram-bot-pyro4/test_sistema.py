"""Pruebas locales: python mfa-telegram-bot-pyro4/test_sistema.py.

Telegram se simula; RPC usa puertos locales temporales. No requiere un token real.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from io import BytesIO
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
import unittest
from unittest.mock import Mock, call, patch
from urllib.error import URLError

import Pyro4
from Pyro4.naming import startNS
from Pyro4.util import SerpentSerializer

from autenticacion import ServicioAutenticacion, Usuario
import cliente
import configuracion
from excepciones import (
    CodigoExpirado,
    CodigoIncorrecto,
    CuentaBloqueada,
    CredencialesInvalidas,
    ErrorAutenticacion,
    ErrorTelegram,
)
import servidor
import telegram_bot
from telegram_bot import BotTelegram


PASSWORD = "Clave-de-prueba-ñ"
CODIGO = "000042"
CODIGO_INCORRECTO = "654321"
TOKEN = "token-ficticio"


class PruebaConParches(unittest.TestCase):
    def parchear(self, destino, **opciones):
        parche = patch(destino, **opciones)
        resultado = parche.start()
        self.addCleanup(parche.stop)
        return resultado


class PruebasUsuario(unittest.TestCase):
    def test_password_correcto_e_incorrecto(self):
        usuario = Usuario.crear(PASSWORD, "000123")

        self.assertTrue(usuario.comprobar_password(PASSWORD))
        self.assertFalse(usuario.comprobar_password("otra-clave"))
        self.assertEqual(usuario.chat_id, "123")
        self.assertIsInstance(usuario.resumen_password, bytes)
        self.assertNotEqual(usuario.resumen_password, PASSWORD.encode("utf-8"))
        with self.assertRaises(FrozenInstanceError):
            usuario.chat_id = "456"

    def test_cada_usuario_tiene_una_sal_diferente(self):
        primero = Usuario.crear(PASSWORD, 123)
        segundo = Usuario.crear(PASSWORD, 456)

        self.assertEqual(len(primero.sal), 16)
        self.assertNotEqual(primero.sal, segundo.sal)
        self.assertNotEqual(primero.resumen_password, segundo.resumen_password)

    def test_rechaza_password_invalido(self):
        for password in (None, 123, "", "a" * 1025):
            with self.subTest(password=password), self.assertRaises(ValueError):
                Usuario.crear(password, 123)

    def test_acepta_password_de_longitud_maxima(self):
        usuario = Usuario.crear("a" * 1024, 123)
        self.assertTrue(usuario.comprobar_password("a" * 1024))

    def test_rechaza_chat_que_no_es_privado_positivo(self):
        for chat_id in (None, "", "abc", 0, -123, "1.5", "１２３", " 123 "):
            with self.subTest(chat_id=chat_id), self.assertRaises(ValueError):
                Usuario.crear(PASSWORD, chat_id)


class PruebasServicio(PruebaConParches):
    @classmethod
    def setUpClass(cls):
        cls.usuarios = {
            "ana": Usuario.crear(PASSWORD, 123),
            "luis": Usuario.crear(PASSWORD, 456),
        }

    def setUp(self):
        self.telegram = Mock(spec=BotTelegram)
        self.reloj = Mock(return_value=100.0)
        self.servicio = ServicioAutenticacion(self.usuarios, self.telegram, reloj=self.reloj)
        self.parchear("autenticacion.Pyro4.current_context.client", new=object())
        self.aleatorio = self.parchear("autenticacion.secrets.randbelow", return_value=42)

    def iniciar_sesion(self, usuario="ana"):
        return self.servicio.iniciar_sesion(usuario, PASSWORD)

    def fallar_password(self):
        with self.assertRaises(CredencialesInvalidas):
            self.servicio.iniciar_sesion("ana", "incorrecta")

    def bloquear_cuenta(self):
        self.fallar_password()
        self.fallar_password()
        with self.assertRaises(CuentaBloqueada):
            self.servicio.iniciar_sesion("ana", "incorrecta")

    def test_login_envia_seis_digitos_sin_devolver_el_codigo(self):
        mensaje = self.iniciar_sesion()

        self.telegram.enviar_codigo.assert_called_once_with("123", CODIGO, 180)
        self.aleatorio.assert_called_once_with(1_000_000)
        self.assertIn("180", mensaje)
        self.assertNotIn(CODIGO, mensaje)
        self.assertNotIn(PASSWORD, mensaje)

    def test_codigo_correcto_se_consume(self):
        self.iniciar_sesion()
        self.assertTrue(self.servicio.verificar_codigo_mfa("ana", CODIGO))

        with self.assertRaises(CodigoIncorrecto):
            self.servicio.verificar_codigo_mfa("ana", CODIGO)

    def test_usuarios_desconocidos_o_invalidos(self):
        for usuario in ("desconocido", "", None, 12, []):
            with self.subTest(usuario=usuario):
                with self.assertRaises(CredencialesInvalidas):
                    self.servicio.iniciar_sesion(usuario, PASSWORD)
                with self.assertRaises(CredencialesInvalidas):
                    self.servicio.verificar_codigo_mfa(usuario, CODIGO)
        self.telegram.enviar_codigo.assert_not_called()

    def test_password_invalido_no_envia_codigo(self):
        for password in (None, 123, "", "incorrecta", "a" * 1025):
            with self.subTest(password=password):
                servicio = ServicioAutenticacion(self.usuarios, self.telegram)
                with self.assertRaises(CredencialesInvalidas):
                    servicio.iniciar_sesion("ana", password)
        self.telegram.enviar_codigo.assert_not_called()

    def test_no_verifica_sin_primer_factor(self):
        with self.assertRaises(CodigoIncorrecto):
            self.servicio.verificar_codigo_mfa("ana", CODIGO)

    def test_otro_cliente_no_puede_validar_ni_gastar_intentos(self):
        self.iniciar_sesion()
        with patch.object(Pyro4.current_context, "client", object()):
            for _ in range(4):
                with self.assertRaises(CodigoIncorrecto):
                    self.servicio.verificar_codigo_mfa("ana", CODIGO)

        self.assertTrue(self.servicio.verificar_codigo_mfa("ana", CODIGO))

    def test_rechaza_codigos_con_formato_incorrecto(self):
        for codigo in (None, 42, "", "00042", "0000042", "abcdef", "１２３４５６", " 00042"):
            with self.subTest(codigo=codigo):
                servicio = ServicioAutenticacion(self.usuarios, self.telegram)
                servicio.iniciar_sesion("ana", PASSWORD)
                with self.assertRaises(CodigoIncorrecto):
                    servicio.verificar_codigo_mfa("ana", codigo)

    def test_permiso_para_reintentar_un_codigo(self):
        self.iniciar_sesion()
        with self.assertRaises(CodigoIncorrecto):
            self.servicio.verificar_codigo_mfa("ana", CODIGO_INCORRECTO)
        self.assertTrue(self.servicio.verificar_codigo_mfa("ana", CODIGO))

    def test_codigo_valido_antes_del_limite(self):
        self.iniciar_sesion()
        self.reloj.return_value = 279.999
        self.assertTrue(self.servicio.verificar_codigo_mfa("ana", CODIGO))

    def test_codigo_expira_en_el_limite_y_se_elimina(self):
        self.iniciar_sesion()
        self.reloj.return_value = 280.0
        with self.assertRaises(CodigoExpirado):
            self.servicio.verificar_codigo_mfa("ana", CODIGO)
        with self.assertRaises(CodigoIncorrecto):
            self.servicio.verificar_codigo_mfa("ana", CODIGO)

    def test_nuevo_envio_reemplaza_codigo_anterior(self):
        self.iniciar_sesion()
        self.aleatorio.return_value = 43
        self.iniciar_sesion()

        with self.assertRaises(CodigoIncorrecto):
            self.servicio.verificar_codigo_mfa("ana", CODIGO)
        self.assertTrue(self.servicio.verificar_codigo_mfa("ana", "000043"))

    def test_error_telegram_invalida_codigo_anterior(self):
        self.iniciar_sesion()
        self.telegram.enviar_codigo.side_effect = ErrorTelegram("Sin conexión")

        with self.assertRaises(ErrorTelegram):
            self.iniciar_sesion()
        with self.assertRaises(CodigoIncorrecto):
            self.servicio.verificar_codigo_mfa("ana", CODIGO)

    def test_vigencia_empieza_despues_del_envio(self):
        def simular_demora(*argumentos):
            self.reloj.return_value = 150.0

        self.telegram.enviar_codigo.side_effect = simular_demora
        self.iniciar_sesion()
        self.reloj.return_value = 300.0
        self.assertTrue(self.servicio.verificar_codigo_mfa("ana", CODIGO))

    def test_tres_password_incorrectos_bloquean_ambos_factores(self):
        self.iniciar_sesion()
        self.bloquear_cuenta()

        with self.assertRaises(CuentaBloqueada):
            self.iniciar_sesion()
        with self.assertRaises(CuentaBloqueada):
            self.servicio.verificar_codigo_mfa("ana", CODIGO)
        self.assertEqual(self.telegram.enviar_codigo.call_count, 1)

    def test_fallos_de_password_y_mfa_se_acumulan_entre_envios(self):
        self.fallar_password()
        self.iniciar_sesion()
        with self.assertRaises(CodigoIncorrecto):
            self.servicio.verificar_codigo_mfa("ana", CODIGO_INCORRECTO)
        self.iniciar_sesion()
        with self.assertRaises(CuentaBloqueada):
            self.servicio.verificar_codigo_mfa("ana", CODIGO_INCORRECTO)

    def test_bloqueo_termina_en_el_limite_e_invalida_codigo(self):
        self.iniciar_sesion()
        self.bloquear_cuenta()
        self.reloj.return_value = 159.1
        with self.assertRaisesRegex(CuentaBloqueada, "1 segundos"):
            self.iniciar_sesion()
        self.reloj.return_value = 160.0
        with self.assertRaises(CodigoIncorrecto):
            self.servicio.verificar_codigo_mfa("ana", CODIGO)
        self.fallar_password()
        self.iniciar_sesion()
        self.assertTrue(self.servicio.verificar_codigo_mfa("ana", CODIGO))

    def test_mfa_correcto_reinicia_intentos(self):
        self.fallar_password()
        self.fallar_password()
        self.iniciar_sesion()
        self.servicio.verificar_codigo_mfa("ana", CODIGO)
        self.fallar_password()

    def test_bloqueo_de_una_cuenta_no_afecta_otra(self):
        self.bloquear_cuenta()
        self.iniciar_sesion("luis")
        self.telegram.enviar_codigo.assert_called_once_with("456", CODIGO, 180)
        self.assertTrue(self.servicio.verificar_codigo_mfa("luis", CODIGO))

    def test_parametros_personalizados(self):
        servicio = ServicioAutenticacion(
            self.usuarios, self.telegram, validez=10, limite_intentos=1,
            tiempo_bloqueo=5, reloj=self.reloj,
        )
        servicio.iniciar_sesion("ana", PASSWORD)
        self.telegram.enviar_codigo.assert_called_once_with("123", CODIGO, 10)
        with self.assertRaises(CuentaBloqueada):
            servicio.verificar_codigo_mfa("ana", CODIGO_INCORRECTO)
        self.reloj.return_value = 105.0
        servicio.iniciar_sesion("ana", PASSWORD)
        self.reloj.return_value = 115.0
        with self.assertRaises(CodigoExpirado):
            servicio.verificar_codigo_mfa("ana", CODIGO)

    def test_dos_validaciones_simultaneas_solo_autorizan_una_vez(self):
        self.iniciar_sesion()
        conexion = Pyro4.current_context.client
        salida = Event()

        def verificar():
            Pyro4.current_context.client = conexion
            if not salida.wait(timeout=5):
                raise TimeoutError("No se iniciaron las verificaciones")
            try:
                return self.servicio.verificar_codigo_mfa("ana", CODIGO)
            except CodigoIncorrecto:
                return False

        with ThreadPoolExecutor(max_workers=2) as ejecutor:
            resultados = [ejecutor.submit(verificar) for _ in range(2)]
            salida.set()
            self.assertCountEqual([resultado.result(timeout=5) for resultado in resultados], [True, False])

    def test_envio_lento_no_detiene_a_otros_usuarios(self):
        enviando = Event()
        continuar = Event()

        def enviar(chat_id, codigo, validez):
            if chat_id == "123":
                enviando.set()
                if not continuar.wait(timeout=5):
                    raise TimeoutError("El envío de prueba no fue liberado")

        self.telegram.enviar_codigo.side_effect = enviar
        with ThreadPoolExecutor(max_workers=2) as ejecutor:
            primero = ejecutor.submit(self.iniciar_sesion)
            try:
                self.assertTrue(enviando.wait(timeout=5))
                segundo = ejecutor.submit(self.iniciar_sesion, "luis")
                self.assertIn("enviado", segundo.result(timeout=5))
            finally:
                continuar.set()
            primero.result(timeout=5)


class PruebasConfiguracion(PruebaConParches):
    def setUp(self):
        temporal = TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.carpeta = Path(temporal.name)
        self.parchear("configuracion.__file__", new=str(self.carpeta / "configuracion.py"))
        entorno = patch.dict(os.environ, {}, clear=True)
        entorno.start()
        self.addCleanup(entorno.stop)
        self.entrada = self.parchear("configuracion.getpass", return_value=" token-consola ")

    def guardar_token(self, contenido):
        (self.carpeta / ".telegram_token").write_text(contenido, encoding="utf-8")

    def test_variable_de_entorno_tiene_prioridad(self):
        os.environ["TELEGRAM_BOT_TOKEN"] = " token-entorno "
        self.guardar_token("token-archivo")
        self.assertEqual(configuracion.obtener_token(), "token-entorno")
        self.entrada.assert_not_called()

    def test_lee_archivo_si_variable_esta_vacia(self):
        os.environ["TELEGRAM_BOT_TOKEN"] = " "
        self.guardar_token(" token-archivo\n")
        self.assertEqual(configuracion.obtener_token(), "token-archivo")
        self.entrada.assert_not_called()

    def test_pide_token_si_archivo_no_existe(self):
        self.assertEqual(configuracion.obtener_token(), "token-consola")
        self.entrada.assert_called_once()

    def test_pide_token_si_archivo_esta_vacio(self):
        self.guardar_token(" \n")
        self.assertEqual(configuracion.obtener_token(), "token-consola")
        self.entrada.assert_called_once()


class PruebasTelegram(PruebaConParches):
    def setUp(self):
        self.bot = BotTelegram(f" {TOKEN} ")
        self.http = self.parchear("telegram_bot.urlopen")

    def responder(self, resultado):
        self.http.return_value = BytesIO(json.dumps(resultado).encode("utf-8"))

    def test_rechaza_token_vacio_o_invalido(self):
        for token in (None, 123, "", "   "):
            with self.subTest(token=token), self.assertRaises(ValueError):
                BotTelegram(token)

    def test_envia_codigo_por_post_json(self):
        self.responder({"ok": True, "result": {"message_id": 1}})
        self.bot.enviar_codigo("123", CODIGO, 180)

        peticion = self.http.call_args.args[0]
        self.assertEqual(peticion.full_url, f"https://api.telegram.org/bot{TOKEN}/sendMessage")
        self.assertEqual(peticion.get_method(), "POST")
        self.assertEqual(peticion.get_header("Content-type"), "application/json")
        self.assertEqual(self.http.call_args.kwargs, {"timeout": 10})
        self.assertEqual(json.loads(peticion.data), {
            "chat_id": "123",
            "text": f"Tu código MFA es: {CODIGO}\nVálido durante 180 segundos. No lo compartas.",
        })

    def test_filtra_chats_privados_ordena_y_elimina_duplicados(self):
        eventos = [
            {"message": {"chat": {"id": 456, "type": "private"}}},
            {"message": {"chat": {"id": -1, "type": "group"}}},
            {"message": {"chat": {"id": 123, "type": "private"}}},
            {"message": {"chat": {"id": 123, "type": "private"}}},
            {"channel_post": {"chat": {"id": -2, "type": "channel"}}},
            {},
        ]
        self.responder({"ok": True, "result": eventos})
        self.assertEqual(self.bot.consultar_chat_ids(), [123, 456])
        peticion = self.http.call_args.args[0]
        self.assertTrue(peticion.full_url.endswith("/getUpdates"))
        self.assertEqual(json.loads(peticion.data), {"allowed_updates": ["message"]})

    def test_consulta_sin_mensajes(self):
        self.responder({"ok": True, "result": []})
        self.assertEqual(self.bot.consultar_chat_ids(), [])

    def test_respuestas_rechazadas_o_incompletas(self):
        for resultado in ([], None, {}, {"ok": False, "result": []}, {"ok": 1, "result": []}, {"ok": True}):
            with self.subTest(resultado=resultado):
                self.responder(resultado)
                with self.assertRaises(ErrorTelegram):
                    self.bot.consultar_chat_ids()

    def test_errores_de_red_no_exponen_token(self):
        for tipo_error in (URLError, OSError):
            with self.subTest(tipo_error=tipo_error):
                self.http.side_effect = tipo_error(f"Error al solicitar /bot{TOKEN}")
                with self.assertRaises(ErrorTelegram) as resultado:
                    self.bot.consultar_chat_ids()
                self.assertNotIn(TOKEN, str(resultado.exception))
                self.assertTrue(resultado.exception.__suppress_context__)

    def test_json_invalido_se_traduce_a_error_telegram(self):
        self.http.return_value = BytesIO(b"respuesta que no es JSON")
        with self.assertRaises(ErrorTelegram):
            self.bot.consultar_chat_ids()

    def test_utilidad_muestra_identificadores(self):
        self.parchear("telegram_bot.obtener_token", return_value=TOKEN)
        self.responder({"ok": True, "result": [{"message": {"chat": {"id": 123, "type": "private"}}}]})
        salida = self.parchear("builtins.print")
        telegram_bot.main()
        salida.assert_called_once_with("chat_id de chat privado: 123")

    def test_utilidad_indica_como_iniciar_chat(self):
        self.parchear("telegram_bot.obtener_token", return_value=TOKEN)
        self.responder({"ok": True, "result": []})
        salida = self.parchear("builtins.print")
        telegram_bot.main()
        self.assertIn("/start", salida.call_args.args[0])

    def test_utilidad_maneja_errores_y_cancelacion(self):
        obtener = self.parchear("telegram_bot.obtener_token")
        salida = self.parchear("builtins.print")
        errores = (
            ErrorTelegram("Sin conexión"), ValueError("Token inválido"),
            EOFError(), KeyboardInterrupt(),
        )
        for error in errores:
            with self.subTest(error=type(error)):
                salida.reset_mock()
                obtener.side_effect = error
                telegram_bot.main()
                salida.assert_called_once()


class PruebasExcepciones(unittest.TestCase):
    def test_excepciones_conservan_tipo_y_mensaje_en_pyro(self):
        serializador = SerpentSerializer()
        tipos = (
            ErrorAutenticacion, CredencialesInvalidas, CodigoExpirado,
            CodigoIncorrecto, CuentaBloqueada, ErrorTelegram,
        )
        for tipo in tipos:
            with self.subTest(tipo=tipo):
                original = tipo("Mensaje de prueba")
                recibido = serializador.loads(serializador.dumps(original))
                self.assertIs(type(recibido), tipo)
                self.assertIsInstance(recibido, ErrorAutenticacion)
                self.assertEqual(recibido.args, original.args)


class PruebasCliente(PruebaConParches):
    def setUp(self):
        self.entrada = self.parchear("builtins.input", side_effect=[" ana ", CODIGO])
        self.parchear("cliente.getpass", return_value=PASSWORD)
        self.salida = self.parchear("builtins.print")
        self.proxy = self.parchear("cliente.Pyro4.Proxy")
        self.servicio = self.proxy.return_value.__enter__.return_value
        self.servicio.iniciar_sesion.return_value = "Código enviado"
        self.servicio.verificar_codigo_mfa.return_value = True

    def test_login_completo_conserva_proxy(self):
        cliente.main()
        direccion = f"PYRONAME:autenticacion.mfa@{Pyro4.config.NS_HOST}:{Pyro4.config.NS_PORT}"
        self.proxy.assert_called_once_with(direccion)
        self.servicio.iniciar_sesion.assert_called_once_with("ana", PASSWORD)
        self.servicio.verificar_codigo_mfa.assert_called_once_with("ana", CODIGO)
        self.assertEqual(self.servicio._pyroTimeout, 20)
        self.salida.assert_any_call("Acceso autorizado. Autenticación multifactor completada.")
        self.proxy.return_value.__exit__.assert_called_once()

    def test_codigo_incorrecto_permite_reintentar(self):
        self.entrada.side_effect = ["ana", CODIGO_INCORRECTO, CODIGO]
        self.servicio.verificar_codigo_mfa.side_effect = [CodigoIncorrecto("Reintenta"), True]
        cliente.main()
        self.assertEqual(self.servicio.verificar_codigo_mfa.call_args_list, [
            call("ana", CODIGO_INCORRECTO), call("ana", CODIGO),
        ])

    def test_salir_cancela_verificacion(self):
        self.entrada.side_effect = ["ana", " SALIR "]
        cliente.main()
        self.servicio.verificar_codigo_mfa.assert_not_called()

    def test_maneja_errores_de_autenticacion(self):
        for tipo in (CredencialesInvalidas, CodigoExpirado, CuentaBloqueada, ErrorTelegram):
            with self.subTest(tipo=tipo):
                self.entrada.side_effect = ["ana", CODIGO]
                error = tipo("Operación rechazada")
                self.servicio.iniciar_sesion.side_effect = error
                cliente.main()
                self.salida.assert_called_with(error)

    def test_error_final_de_verificacion_termina_cliente(self):
        self.servicio.verificar_codigo_mfa.side_effect = CodigoExpirado("Expirado")
        cliente.main()
        self.assertEqual(str(self.salida.call_args.args[0]), "Expirado")

    def test_maneja_fallo_de_conexion(self):
        self.proxy.side_effect = Pyro4.errors.CommunicationError("Sin conexión")
        cliente.main()
        self.assertIn("No se pudo conectar", self.salida.call_args.args[0])

    def test_maneja_cancelacion(self):
        for tipo in (EOFError, KeyboardInterrupt):
            with self.subTest(tipo=tipo):
                self.entrada.side_effect = tipo
                cliente.main()
                self.assertIn("cancelado", self.salida.call_args.args[0])


class PruebasServidor(PruebaConParches):
    def setUp(self):
        self.salida = self.parchear("builtins.print")
        self.entrada = self.parchear("builtins.input")
        self.password = self.parchear("servidor.getpass", return_value=PASSWORD)

    def preparar_servidor(self):
        self.daemon = self.parchear("servidor.Pyro4.Daemon").return_value.__enter__.return_value
        self.localizar = self.parchear("servidor.Pyro4.locateNS")
        self.registro = self.localizar.return_value.__enter__.return_value
        self.parchear("servidor.obtener_token", return_value=TOKEN)
        self.parchear("servidor.registrar_usuarios", return_value={})
        self.registro.lookup.return_value = self.daemon.register.return_value

    def test_registro_exige_una_cuenta_y_rechaza_duplicados(self):
        self.entrada.side_effect = ["", " ana ", " 123 ", "ana", ""]
        usuarios = servidor.registrar_usuarios()
        self.assertEqual(list(usuarios), ["ana"])
        self.assertTrue(usuarios["ana"].comprobar_password(PASSWORD))
        self.assertEqual(usuarios["ana"].chat_id, "123")
        self.password.assert_called_once()
        self.salida.assert_any_call("Debes registrar al menos un usuario.")
        self.salida.assert_any_call("Ese usuario ya fue registrado.")

    def test_registro_recupera_datos_invalidos(self):
        self.entrada.side_effect = ["ana", "-1", "ana", "123", ""]
        usuarios = servidor.registrar_usuarios()
        self.assertEqual(list(usuarios), ["ana"])
        self.assertEqual(self.password.call_count, 2)

    def test_registra_servicio_y_limpia_name_server_al_cerrar(self):
        self.preparar_servidor()
        servidor.main()
        servicio = self.daemon.register.call_args.args[0]
        self.assertIsInstance(servicio, ServicioAutenticacion)
        self.localizar.assert_called_once_with(host=Pyro4.config.NS_HOST, port=Pyro4.config.NS_PORT)
        self.registro.register.assert_called_once_with("autenticacion.mfa", self.daemon.register.return_value)
        self.daemon.requestLoop.assert_called_once()
        self.registro.remove.assert_called_once_with("autenticacion.mfa")

    def test_no_elimina_registro_reemplazado(self):
        self.preparar_servidor()
        self.registro.lookup.return_value = "PYRO:otro@127.0.0.1:12345"
        servidor.main()
        self.registro.remove.assert_not_called()

    def test_error_durante_limpieza_es_controlado(self):
        self.preparar_servidor()
        self.registro.lookup.side_effect = Pyro4.errors.NamingError("Registro cerrado")
        servidor.main()
        self.registro.remove.assert_not_called()

    def test_maneja_name_server_no_disponible(self):
        self.preparar_servidor()
        for tipo in (Pyro4.errors.NamingError, Pyro4.errors.CommunicationError):
            with self.subTest(tipo=tipo):
                self.localizar.side_effect = tipo("No disponible")
                servidor.main()
                self.assertIn("python -m Pyro4.naming", self.salida.call_args.args[0])

    def test_configuracion_invalida_es_controlada(self):
        self.preparar_servidor()
        self.parchear("servidor.obtener_token", side_effect=ValueError("Token inválido"))
        servidor.main()
        self.assertEqual(str(self.salida.call_args.args[0]), "Token inválido")
        self.daemon.register.assert_not_called()

    def test_cancelacion_limpia_registro(self):
        self.preparar_servidor()
        for tipo in (EOFError, KeyboardInterrupt):
            with self.subTest(tipo=tipo):
                self.registro.remove.reset_mock()
                self.daemon.requestLoop.side_effect = tipo
                servidor.main()
                self.registro.remove.assert_called_once_with("autenticacion.mfa")
                self.assertIn("cerrado", self.salida.call_args.args[0])


class PruebasRPC(PruebaConParches):
    """Ejercita sockets y serialización reales, con Telegram simulado."""

    @classmethod
    def setUpClass(cls):
        cls.usuario = Usuario.crear(PASSWORD, 123)

    def iniciar_daemon(self, daemon):
        self.addCleanup(daemon.close)
        hilo = Thread(target=daemon.requestLoop, daemon=True)
        hilo.start()
        self.addCleanup(self.detener_daemon, daemon, hilo)

    def detener_daemon(self, daemon, hilo):
        daemon.shutdown()
        hilo.join(timeout=5)
        self.assertFalse(hilo.is_alive(), "El servidor temporal no se cerró")

    def setUp(self):
        self.parchear("Pyro4.config.SERVERTYPE", new="thread")
        self.parchear("Pyro4.config.COMMTIMEOUT", new=3.0)
        self.parchear("autenticacion.secrets.randbelow", return_value=42)
        uri_nombres, nombres, _ = startNS(host="127.0.0.1", port=0, enableBroadcast=False)
        self.iniciar_daemon(nombres)
        self.parchear("Pyro4.config.NS_HOST", new="127.0.0.1")
        self.parchear("Pyro4.config.NS_PORT", new=uri_nombres.port)
        self.telegram = Mock(spec=BotTelegram)
        servicio = ServicioAutenticacion({"ana": self.usuario}, self.telegram)
        daemon = Pyro4.Daemon(host="127.0.0.1", port=0)
        self.iniciar_daemon(daemon)
        uri = daemon.register(servicio)
        with Pyro4.locateNS(host="127.0.0.1", port=uri_nombres.port) as registro:
            registro.register("autenticacion.mfa", uri)
        self.direccion = f"PYRONAME:autenticacion.mfa@127.0.0.1:{uri_nombres.port}"

    def test_cliente_completa_mfa_sobre_rpc_real(self):
        self.parchear("builtins.input", side_effect=["ana", CODIGO])
        self.parchear("cliente.getpass", return_value=PASSWORD)
        salida = self.parchear("builtins.print")
        cliente.main()
        salida.assert_any_call("Acceso autorizado. Autenticación multifactor completada.")
        self.telegram.enviar_codigo.assert_called_once_with("123", CODIGO, 180)

    def test_otra_conexion_no_valida_y_codigo_no_se_reutiliza(self):
        with Pyro4.Proxy(self.direccion) as primero, Pyro4.Proxy(self.direccion) as segundo:
            primero.iniciar_sesion("ana", PASSWORD)
            with self.assertRaises(CodigoIncorrecto):
                segundo.verificar_codigo_mfa("ana", CODIGO)
            self.assertTrue(primero.verificar_codigo_mfa("ana", CODIGO))
            with self.assertRaises(CodigoIncorrecto):
                primero.verificar_codigo_mfa("ana", CODIGO)

    def test_error_telegram_llega_al_cliente_sin_activar_codigo(self):
        self.telegram.enviar_codigo.side_effect = ErrorTelegram("Telegram no disponible")
        with Pyro4.Proxy(self.direccion) as proxy:
            with self.assertRaisesRegex(ErrorTelegram, "Telegram no disponible"):
                proxy.iniciar_sesion("ana", PASSWORD)
            with self.assertRaises(CodigoIncorrecto):
                proxy.verificar_codigo_mfa("ana", CODIGO)


if __name__ == "__main__":
    unittest.main(verbosity=2)
