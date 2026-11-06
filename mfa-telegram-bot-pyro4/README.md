# Autenticación MFA con Telegram y Pyro4

El servidor comprueba usuario y contraseña, envía un código de 6 dígitos por
Telegram y autoriza el acceso cuando el cliente devuelve ese código. La misma
conexión Pyro4 realiza ambos pasos.

## Preparación

Requiere Python 3.10 o superior.

Desde la raíz del proyecto, con el entorno `.venv` activado:

```powershell
python -m pip install -r mfa-telegram-bot-pyro4\requirements.txt
```

1. En Telegram, abre [@BotFather](https://t.me/BotFather), utiliza `/newbot` y
   sigue sus instrucciones para obtener el token de tu bot.
2. Abre una conversación privada con tu nuevo bot y envía `/start`. Cada usuario
   que recibirá códigos debe iniciar su propia conversación con el bot.
3. Consulta los identificadores de esos chats:

   ```powershell
   python mfa-telegram-bot-pyro4\telegram_bot.py
   ```

   La utilidad carga el token configurado (o lo pide sin mostrarlo) y consulta `getUpdates`. Muestra solo
   los `chat_id` de conversaciones privadas, sin imprimir los mensajes ni el
   token. Si no hay resultados, envía un nuevo mensaje al bot y repite la consulta.
   Relaciona cada identificador con su usuario al configurar el servidor; puedes
   hacer la consulta después de que cada persona envíe su primer mensaje.

El token se obtiene, en orden, de la variable de entorno `TELEGRAM_BOT_TOKEN`,
del archivo local `.telegram_token` de esta carpeta o de una entrada oculta en
la consola. El archivo está excluido de Git y debe permanecer únicamente en la
computadora servidor. El cliente no necesita conocer el token.

Referencias oficiales: [crear un bot](https://core.telegram.org/bots/features#botfather),
[getUpdates](https://core.telegram.org/bots/api#getupdates) y
[sendMessage](https://core.telegram.org/bots/api#sendmessage).

## Ejecución local

Abre tres terminales en la raíz del proyecto, con `.venv` activado.

1. Servidor de nombres, si todavía no está activo:

   ```powershell
   python -m Pyro4.naming
   ```

2. Servidor de autenticación:

   ```powershell
   python mfa-telegram-bot-pyro4\servidor.py
   ```

   Si no hay un token configurado, ingrésalo cuando se solicite. Registra cada usuario con su contraseña y su
   `chat_id` privado. Deja el nombre de usuario vacío para terminar el registro
   y comenzar a atender conexiones. Debes registrar al menos una cuenta.

3. Cliente:

   ```powershell
   python mfa-telegram-bot-pyro4\cliente.py
   ```

   Ingresa el usuario y la contraseña configurados en el servidor. Recibirás el
   código en Telegram. Escríbelo completo, incluyendo ceros iniciales si los hay.
   Si es correcto, aparece `Acceso autorizado`. Puedes escribir `salir` para cancelar.

Para conectar otro cliente, abre otra terminal y repite el último comando.

## Reglas de autenticación

- El servicio se registra como `autenticacion.mfa` en el Name Server.
- Los códigos se generan con `secrets`, tienen 6 dígitos y duran 180 segundos
  desde que Telegram confirma el envío. No se devuelven al cliente por Pyro4.
- Solo se guarda el hash del código. Un nuevo envío reemplaza al anterior y una
  validación correcta lo consume; no puede reutilizarse.
- La verificación exige la conexión que comprobó la contraseña. Otro cliente
  no puede validar ese código ni gastar sus intentos MFA.
- Se suman los fallos de contraseña y de código para cada cuenta registrada.
  Al tercer fallo se bloquea durante 60 segundos y se invalida su código.
  Solicitar otro código no reinicia este contador. Se reinicia después de un MFA
  correcto o al terminar el bloqueo.
- Un código expirado se elimina. Si Telegram falla, no se activa un código ni
  se anuncia un envío exitoso.
- Cada usuario tiene su propio bloqueo para evitar validaciones simultáneas y
  permitir que otras cuentas continúen mientras se envía un mensaje a Telegram.
- Las contraseñas se almacenan en memoria como hashes PBKDF2-HMAC-SHA256, con
  sal aleatoria y 600 000 iteraciones; no se conserva la contraseña original.
- Las cuentas, códigos y bloqueos permanecen en memoria. Al reiniciar el servidor
  debes registrar nuevamente los usuarios.

Las excepciones personalizadas `CredencialesInvalidas`, `CodigoExpirado`,
`CodigoIncorrecto`, `CuentaBloqueada` y `ErrorTelegram` se registran para que Pyro4
las transmita al cliente. Los errores HTTP no muestran la URL que contiene el token.

## Otras computadoras

Usa la IPv4 real del servidor; este ejemplo utiliza `172.17.44.103`.

En el servidor, primera terminal:

```powershell
python -m Pyro4.naming -n 172.17.44.103 -p 9090
```

En el servidor, segunda terminal:

```powershell
$env:PYRO_HOST = "172.17.44.103"
$env:PYRO_NS_HOST = "172.17.44.103"
python mfa-telegram-bot-pyro4\servidor.py
```

En cada cliente:

```powershell
$env:PYRO_NS_HOST = "172.17.44.103"
python mfa-telegram-bot-pyro4\cliente.py
```

Ambos servidores deben mantenerse abiertos. El servicio consulta directamente
el Name Server indicado, sin búsqueda automática de otros equipos. El envío a
Telegram usa HTTPS. Pyro4 no cifra las credenciales por defecto: las pruebas
sin TLS deben limitarse a un entorno local controlado; para redes no confiables
se requiere configurar TLS también en Pyro4.
