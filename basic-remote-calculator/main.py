import Pyro4

@Pyro4.expose
class Calc(object):

  def sumar(self, a, b):
    return a + b

  def restar(self, a, b):
    return a - b

  def multiplicar(self, a, b):
    return a * b

  def dividir(self, a, b):
    if b == 0:
      return "Error: División por cero"
    return a / b

daemon = Pyro4.Daemon()
ns = Pyro4.locateNS()
uri = daemon.register(Calc)
ns.register("calculadora", uri)

print("Servidor de calculadora listo.")
daemon.requestLoop()