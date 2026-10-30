import Pyro4

# Conectar al objeto remoto en el Name Server
calc = Pyro4.Proxy("PYRONAME:calculadora")

print("--- Calculadora Remota con Pyro4 ---")
try:
  num1 = float(input("Ingresa el primer dígito (número): "))
  num2 = float(input("Ingresa el segundo dígito (número): "))
except ValueError:
  print("Por favor, ingresa números válidos.")
  exit()

print("\nSelecciona una operación:")
print("1. Sumar")
print("2. Restar")
print("3. Multiplicar")
print("4. Dividir")

opcion = input("Opción (1-4): ").strip()

if opcion == "1":
  resultado = calc.sumar(num1, num2)
  print(f"Resultado: {resultado}")
elif opcion == "2":
  resultado = calc.restar(num1, num2)
  print(f"Resultado: {resultado}")
elif opcion == "3":
  resultado = calc.multiplicar(num1, num2)
  print(f"Resultado: {resultado}")
elif opcion == "4":
  resultado = calc.dividir(num1, num2)
  print(f"Resultado: {resultado}")
else:
  print("Opción inválida.")