from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Caja, DetalleVenta, Empleado, Gasto, Producto, Tienda, Venta


Usuario = get_user_model()


class TiendaFlowTests(TestCase):
	def setUp(self):
		self.client = APIClient()
		self.owner = Usuario.objects.create_user(
			username="owner",
			email="owner@example.com",
			password="testpass123",
			rol=Usuario.Rol.ADMINISTRADOR,
		)
		self.vendor_one = Usuario.objects.create_user(
			username="vendor1",
			email="vendor1@example.com",
			password="testpass123",
			rol=Usuario.Rol.VENDEDOR,
		)
		self.vendor_two = Usuario.objects.create_user(
			username="vendor2",
			email="vendor2@example.com",
			password="testpass123",
			rol=Usuario.Rol.VENDEDOR,
		)
		self.tienda = Tienda.objects.create(
			nombre="Tienda central",
			direccion="Calle 1",
			propietario=self.owner,
		)
		self.client.force_authenticate(user=self.owner)

	def test_lista_vendedores_y_asigna_por_usuario_id(self):
		respuesta = self.client.get(f"/api/tiendas/{self.tienda.id}/vendedores/")

		self.assertEqual(respuesta.status_code, 200)
		self.assertEqual(len(respuesta.data["vendedores"]), 2)

		respuesta = self.client.post(
			f"/api/tiendas/{self.tienda.id}/agregar_empleado/",
			{"usuario_id": self.vendor_one.id},
			format="json",
		)

		self.assertEqual(respuesta.status_code, 200)
		self.assertTrue(Empleado.objects.filter(usuario=self.vendor_one, tienda=self.tienda).exists())

	def test_venta_no_descuenta_stock_si_falla_una_linea(self):
		Caja.objects.create(
			tienda=self.tienda,
			usuario=self.owner,
			turno="mañana",
			saldo_inicial=Decimal("100.00"),
		)
		producto_ok = Producto.objects.create(
			tienda=self.tienda,
			nombre="Producto OK",
			categoria="General",
			precio=Decimal("10.00"),
			cantidad=5,
		)
		producto_falla = Producto.objects.create(
			tienda=self.tienda,
			nombre="Producto Falla",
			categoria="General",
			precio=Decimal("20.00"),
			cantidad=1,
		)

		respuesta = self.client.post(
			"/api/ventas/",
			{
				"tienda_id": self.tienda.id,
				"productos": [
					{"producto": producto_ok.id, "cantidad": 1},
					{"producto": producto_falla.id, "cantidad": 3},
				],
			},
			format="json",
		)

		self.assertEqual(respuesta.status_code, 400)
		producto_ok.refresh_from_db()
		producto_falla.refresh_from_db()
		self.assertEqual(producto_ok.cantidad, 5)
		self.assertEqual(producto_falla.cantidad, 1)
		self.assertEqual(Venta.objects.count(), 0)
		self.assertEqual(DetalleVenta.objects.count(), 0)

	def test_gasto_crea_registro_con_tienda_activa(self):
		Caja.objects.create(
			tienda=self.tienda,
			usuario=self.owner,
			turno="mañana",
			saldo_inicial=Decimal("100.00"),
		)

		respuesta = self.client.post(
			"/api/gastos/",
			{
				"tienda_id": self.tienda.id,
				"descripcion": "Compra de suministros",
				"monto": "15.50",
				"categoria": "Operativo",
			},
			format="json",
		)

		self.assertEqual(respuesta.status_code, 201)
		self.assertEqual(Gasto.objects.count(), 1)
		gasto = Gasto.objects.first()
		self.assertEqual(gasto.tienda, self.tienda)
		self.assertEqual(gasto.usuario, self.owner)
