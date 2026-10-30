import Pyro4
import time


def main():
    # 1. Obtenemos el proxy normal
    proxy = Pyro4.Proxy("PYRONAME:practica.procesador")

    # 2. Usamos Pyro4.Future para envolver específicamente el metodo que queremos invocar de forma asíncrona
    metodo_asincrono = Pyro4.Future(proxy.procesar_datos_pesados)

    print("Enviando petición de procesamiento al servidor...")

    # 3. Al invocarlo, no bloquea el cliente y devuelve un objeto 'Future' de inmediato
    futuro = metodo_asincrono("Lote_Datos_001")

    print("El cliente no está bloqueado. Ejecutando otras tareas locales...")
    for i in range(1, 6):
        print(f"Trabajando localmente... paso {i}")
        time.sleep(0.8)

    print("\nEsperando el resultado final del servidor (si aún no termina)...")

    # .value bloquea la ejecución SÓLO si el servidor aún no ha terminado los 5 segundos
    resultado = futuro.value
    print("✅ Servidor respondió:", resultado)


if __name__ == "__main__":
    main()