def mostrar_estado(estado):
    """Presentación compartida por la consola del servidor y sus participantes."""
    titulos = {
        "espera": "Sala de espera",
        "preparada": "Subasta preparada",
        "en_curso": "Subasta en curso",
        "finalizada": "Subasta finalizada",
    }
    print(f"\n--- {titulos[estado['fase']]} ---")
    print(f"Participantes: {', '.join(estado['clientes']) or 'Sin participantes'}")
    if estado["fase"] != "espera":
        print(f"Producto: {estado['producto']} | Precio: ${estado['precio_actual']:.2f}")
    if estado["fase"] == "preparada":
        print(f"Duración: {estado['duracion']:g} segundos. Esperando que el servidor inicie.")
    elif estado["fase"] == "en_curso":
        print(
            f"Mejor postor: {estado['mejor_postor'] or 'Sin ofertas'}"
            f" | Tiempo restante: {estado['tiempo_restante']:.1f} s"
        )
    elif estado["finalizada"]:
        print(f"Ganador: {estado['mejor_postor'] or 'Sin ofertas'}.")
        print("El servidor puede preparar otro producto. Los participantes pueden salir o esperar.")
