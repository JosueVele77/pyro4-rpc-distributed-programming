from math import isfinite
import Pyro4
from excepciones import SaldoInsuficiente

@Pyro4.expose
@Pyro4.behavior(instance_mode="session")
class CuentaBancaria:
    def __init__(self):
        # Cada conexión conserva su propia cuenta en memoria.
        self.saldo = 0.0

    def _validar_monto(self, monto):
        if not isfinite(monto) or monto <= 0:
            raise ValueError("El monto debe ser un número positivo y finito.")

    def depositar(self, monto):
        self._validar_monto(monto)
        self.saldo += monto
        return self.saldo

    def retirar(self, monto):
        self._validar_monto(monto)
        if monto > self.saldo:
            raise SaldoInsuficiente("No hay saldo suficiente para realizar el retiro.")

        self.saldo -= monto
        return self.saldo

    def consultar_saldo(self):
        return self.saldo


def main():
    with Pyro4.Daemon() as servidor:
        registro = Pyro4.locateNS()
        # Registrar la clase permite que Pyro4 cree una instancia por sesión.
        uri = servidor.register(CuentaBancaria)
        registro.register("cuenta_bancaria", uri)
        print("Servidor bancario listo. Política de instancia: session.")
        servidor.requestLoop()


if __name__ == "__main__":
    main()
