# Subastas distribuidas en consola

La sala permite conectar varios participantes, preparar productos y realizar
subastas consecutivas sin reiniciar el servidor. El primer participante es el
anfitrión; si sale, el siguiente participante ocupa su lugar.

## Preparación

En cada computadora, desde la raíz del proyecto y con `.venv` activado:

```powershell
python -m pip install -r distributed-auction-system\requirements.txt
```

Ejecuta el cliente en PowerShell o Windows Terminal. `prompt_toolkit` conserva
lo que estás escribiendo cuando llegan notificaciones. El servidor y los clientes
deben utilizar los archivos actualizados.

## Ejecución local

Abre terminales separadas y ejecuta en orden:

```powershell
python -m Pyro4.naming
```

```powershell
python distributed-auction-system\servidor.py
```

```powershell
python distributed-auction-system\cliente.py
```

Repite el último comando para conectar más participantes. La sala empieza vacía:
el tiempo no corre hasta que el anfitrión usa `iniciar`.

## Uso de la sala

1. Cada participante ingresa un nombre diferente.
2. El anfitrión escribe `preparar` y completa producto, precio base y duración
   en segundos. Todos ven el producto preparado.
3. Cuando estén listos, el anfitrión escribe `iniciar`.
4. Los participantes escriben montos, por ejemplo `150`. Solo se acepta una
   oferta superior al precio actual y dentro del plazo.
5. Al terminar se anuncia el ganador, o que no hubo ofertas. El anfitrión puede
   usar `preparar` para otro producto y luego `iniciar`.
6. Cualquier participante puede escribir `salir` o usar Ctrl+C para desconectarse.
   Su nombre se retira de la sala y los demás pueden continuar.

`estado` consulta participantes, producto y plazo restante. `ayuda` muestra
los comandos. Salir no retira una oferta aceptada ni cierra el servidor.

Las actualizaciones llegan por polling cada 0.25 segundos, se muestran encima
del campo de entrada y no repiten la confirmación de tu propia oferta. Las
respuestas antiguas no reemplazan un estado reciente. Una oferta empezada
para un producto anterior se rechaza si ya se preparó otro.

## Varias computadoras

Conecta las computadoras a la misma red. Sustituye `172.17.44.103` por la IPv4
real del servidor. En la computadora servidor, primera terminal:

```powershell
python -m Pyro4.naming -n 172.17.44.103 -p 9090
```

En la misma computadora, segunda terminal:

```powershell
$env:PYRO_HOST = "172.17.44.103"
$env:PYRO_NS_HOST = "172.17.44.103"
python distributed-auction-system\servidor.py
```

En cada computadora cliente:

```powershell
$env:PYRO_NS_HOST = "172.17.44.103"
python distributed-auction-system\cliente.py
```

El Name Server se consulta directamente para evitar encontrar otro servidor
de la red por búsqueda automática. Permite las conexiones entrantes de Python
en el firewall del servidor para la red privada: el Name Server usa TCP 9090
y el servicio de subastas usa un puerto dinámico.

## Estado y errores

Una instancia compartida usa un bloqueo para validar y actualizar las ofertas
sin condiciones de carrera. Los datos incorrectos generan `ValueError` y las
operaciones fuera de fase generan `RuntimeError`, transmitidos por Pyro4.
Los errores de conexión muestran su detalle. El estado permanece en memoria;
reiniciar el servidor crea una sala nueva.
