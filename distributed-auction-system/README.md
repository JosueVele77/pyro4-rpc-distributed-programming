# Subastas distribuidas en consola

El operador configura los productos desde la consola del servidor y realiza
subastas consecutivas sin reiniciarlo. Los clientes se conectan a la sala para
ofertar, consultar el estado y salir; ninguno administra la subasta.

## Preparación

En cada computadora, desde la raíz del proyecto y con `.venv` activado:

```powershell
python -m pip install -r distributed-auction-system\requirements.txt
```

Ejecuta el cliente en PowerShell o Windows Terminal. `prompt_toolkit` conserva
lo que estás escribiendo cuando llegan notificaciones. Copia los archivos
actualizados a cada equipo, incluyendo `consola.py`, compartido por servidor
y cliente.

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
el tiempo no corre hasta que el operador usa `iniciar` en el servidor.

## Uso de la sala

1. En la terminal de `servidor.py`, el operador escribe `preparar` y completa
   producto, precio base y duración en segundos.
2. Los participantes ejecutan `cliente.py` e ingresan nombres diferentes.
   Todos ven el producto preparado en la sala de espera.
3. Cuando estén listos, el operador escribe `iniciar` en el servidor.
4. Los clientes escriben montos, por ejemplo `150`. Solo se acepta una oferta
   superior al precio actual y dentro del plazo.
5. Al terminar se anuncia el ganador, o que no hubo ofertas. El operador puede
   usar `preparar` para otro producto y luego `iniciar`, desde el servidor.
6. Cada cliente puede escribir `salir` o usar Ctrl+C para desconectarse.
   Su nombre se retira de la sala y los demás continúan.

En el cliente, `estado` consulta participantes, producto y plazo restante;
`ayuda` muestra los comandos. `salir` no retira una oferta aceptada ni cierra
el servidor. No hay anfitriones ni permisos de administración para clientes.

En el servidor, los comandos son `preparar`, `iniciar`, `estado`, `ayuda` y
`salir`. Este último, o Ctrl+C, cierra el servicio. Su consola sigue atendiendo
ofertas mientras el operador escribe. Los métodos de preparación e inicio son
privados y Pyro4 rechaza cualquier intento de invocarlos desde un cliente.

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
