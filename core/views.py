from django.db import models
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from rest_framework import viewsets, permissions, status, serializers
from django.contrib.auth import get_user_model
from django.db import transaction
from decimal import Decimal
from .models import Caja, Tienda, Empleado, Producto, Venta, DetalleVenta, Gasto
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.contrib.auth.hashers import make_password
from django.utils.crypto import get_random_string
from django.utils.timezone import now
import random
from .serializers import (
    CajaSerializer, UsuarioSerializer, TiendaSerializer, EmpleadoSerializer, ProductoSerializer, VentaSerializer,
    DetalleVentaSerializer, GastoSerializer
)

# Obtener el modelo de usuario
Usuario = get_user_model()


def _resolve_tienda_id(request):
    return (
        request.data.get("tienda_id")
        or request.data.get("tienda")
        or request.query_params.get("tienda_id")
        or request.session.get("tienda_id")
    )


def _usuario_tiene_acceso_tienda(usuario, tienda):
    if usuario.is_superuser or usuario.is_staff:
        return True
    if tienda.propietario_id == usuario.id:
        return True
    return Empleado.objects.filter(usuario=usuario, tienda=tienda).exists()


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UsuarioSerializer(request.user).data)

# Vista para Usuarios
class UsuarioViewSet(viewsets.ModelViewSet):
    queryset = Usuario.objects.all()
    serializer_class = UsuarioSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        # Generar una contraseña aleatoria temporal
        password_temporal = get_random_string(length=8)  # Ej: 'A2k9Lm3p'
        
        # Guardar el usuario con contraseña encriptada
        usuario = serializer.save(
            password=make_password(password_temporal),
            rol=Usuario.Rol.VENDEDOR,
            is_staff=False,
            is_superuser=False,
        )

        # Guardar la contraseña temporal en el objeto para retornarla en la respuesta
        self.password_temporal = password_temporal

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)

        # Solo si el usuario se creó correctamente
        if hasattr(self, 'password_temporal'):
            response.data['password_temporal'] = self.password_temporal
        
        return response

# Vista para Tiendas
class TiendaViewSet(viewsets.ModelViewSet):
    """
    API para la gestión de tiendas.  
    Los usuarios pueden administrar sus tiendas, agregar y remover empleados, y seleccionar una tienda activa.
    """
    queryset = Tienda.objects.all()
    serializer_class = TiendaSerializer
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Lista las tiendas del usuario autenticado.",
        responses={200: TiendaSerializer(many=True)}
    )
    def get_queryset(self):
        """Filtra tiendas según el usuario autenticado"""
        return Tienda.objects.filter(propietario=self.request.user)

    @swagger_auto_schema(
        operation_description="Crea una nueva tienda y la asigna al usuario autenticado.",
        request_body=TiendaSerializer,
        responses={
            201: TiendaSerializer,
            400: "Error en la creación de la tienda."
        }
    )
    def perform_create(self, serializer):
        """Asigna automáticamente el propietario al usuario autenticado"""
        serializer.save(propietario=self.request.user)

    @swagger_auto_schema(
        operation_description="Lista los empleados de una tienda específica.",
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "empleados": openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                "id": openapi.Schema(type=openapi.TYPE_INTEGER, description="ID del empleado"),
                                "nombre": openapi.Schema(type=openapi.TYPE_STRING, description="Nombre de usuario del empleado")
                            }
                        )
                    )
                }
            )
        }
    )
    @action(detail=True, methods=['get'])
    def empleados(self, request, pk=None):
        """Lista los empleados de una tienda específica"""
        tienda = self.get_object()
        empleados = Empleado.objects.filter(tienda=tienda)
        empleados_data = [
            {"id": empleado.id, "nombre": empleado.usuario.username}
            for empleado in empleados
        ]
        return Response({"empleados": empleados_data})

    @swagger_auto_schema(
        operation_description="Lista todos los vendedores registrados y su estado de asignación a la tienda.",
        responses={200: openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Schema(type=openapi.TYPE_OBJECT))},
    )
    @action(detail=True, methods=['get'], url_path='vendedores')
    def vendedores(self, request, pk=None):
        tienda = self.get_object()
        vendedores = Usuario.objects.filter(rol=Usuario.Rol.VENDEDOR).order_by('username')
        empleados = Empleado.objects.filter(usuario__in=vendedores).select_related('usuario', 'tienda')
        empleados_por_usuario = {empleado.usuario_id: empleado for empleado in empleados}

        vendedores_data = []
        for vendedor in vendedores:
            empleado = empleados_por_usuario.get(vendedor.id)
            vendedores_data.append({
                "id": vendedor.id,
                "username": vendedor.username,
                "email": vendedor.email,
                "telefono": vendedor.telefono,
                "asignado": empleado is not None,
                "tienda_id": empleado.tienda_id if empleado else None,
                "tienda_nombre": empleado.tienda.nombre if empleado else None,
                "puede_asignar": empleado is None,
            })

        return Response({"tienda": {"id": tienda.id, "nombre": tienda.nombre}, "vendedores": vendedores_data})

    @swagger_auto_schema(
        operation_description="Agrega un empleado a una tienda.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "usuario_id": openapi.Schema(type=openapi.TYPE_INTEGER, description="ID del vendedor registrado"),
                "email": openapi.Schema(type=openapi.TYPE_STRING, description="Correo del vendedor registrado, opcional")
            },
            required=["usuario_id"]
        ),
        responses={
            200: "Empleado agregado correctamente.",
            400: "Error en la asignación del empleado."
        }
    )

    @action(detail=True, methods=['post'])
    def agregar_empleado(self, request, pk=None):
        """Asocia un usuario existente como empleado de la tienda activa."""
        tienda = self.get_object()
        usuario_id = request.data.get('usuario_id')
        email = (request.data.get('email') or '').strip()

        usuario = None
        if usuario_id:
            usuario = Usuario.objects.filter(id=usuario_id).first()
        elif email:
            usuarios = Usuario.objects.filter(email__iexact=email)
            if usuarios.count() == 1:
                usuario = usuarios.first()
            elif usuarios.count() > 1:
                return Response(
                    {"error": "Hay múltiples usuarios con ese correo. Use un ID de usuario."},
                    status=400,
                )

        if usuario is None:
            return Response({"error": "Debe proporcionar usuario_id o email de un vendedor registrado."}, status=400)

        if usuario.rol != Usuario.Rol.VENDEDOR:
            return Response({"error": "Solo se pueden asignar usuarios con rol vendedor."}, status=400)

        empleado_existente = Empleado.objects.filter(usuario=usuario).select_related('tienda').first()
        if empleado_existente:
            if empleado_existente.tienda_id == tienda.id:
                return Response({"error": "El usuario ya está asignado a esta tienda."}, status=400)
            return Response({"error": f"El usuario ya está asignado a la tienda {empleado_existente.tienda.nombre}."}, status=400)

        Empleado.objects.create(usuario=usuario, tienda=tienda)

        return Response({
            "mensaje": f"Empleado {usuario.username} agregado a {tienda.nombre}.",
            "usuario_id": usuario.id,
        })

    
    @swagger_auto_schema(
    operation_description="Elimina un empleado de la tienda.",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            "empleado_id": openapi.Schema(type=openapi.TYPE_INTEGER, description="ID del empleado a remover")
        },
        required=["empleado_id"]
    ),
    responses={
        200: "Empleado eliminado correctamente.",
        400: "El empleado no pertenece a esta tienda."
    }
)
    @action(detail=True, methods=['post'])
    def remover_empleado(self, request, pk=None):
        """Elimina un empleado de la tienda"""
        tienda = self.get_object()
        empleado_id = request.data.get('empleado_id')

        if not empleado_id:
            return Response({"error": "Debe proporcionar el ID del empleado a eliminar."}, status=400)

        try:
            empleado = Empleado.objects.get(id=empleado_id, tienda=tienda)
            nombre_empleado = empleado.usuario.username
            empleado.delete()
            return Response({"mensaje": f"Empleado {nombre_empleado} fue eliminado de {tienda.nombre}."})

        except Empleado.DoesNotExist:
            return Response({"error": "El empleado no pertenece a esta tienda o no existe."}, status=400)


    @swagger_auto_schema(
        operation_description="Selecciona una tienda y la almacena en la sesión del usuario.",
        responses={200: "Tienda seleccionada correctamente.", 404: "Tienda no encontrada."}
    )

    @action(detail=True, methods=["post"])
    def seleccionar_tienda(self, request, pk=None):
        """
        Guarda en la sesión la tienda que el usuario está administrando.
        """
        tienda = get_object_or_404(Tienda, id=pk, propietario=request.user)
        request.session["tienda_id"] = tienda.id
        return Response({"mensaje": f"Tienda {tienda.nombre} seleccionada correctamente."})



# Vista para Empleados
class EmpleadoViewSet(viewsets.ModelViewSet):
    queryset = Empleado.objects.all()
    serializer_class = EmpleadoSerializer
    permission_classes = [permissions.IsAuthenticated]

# Vista para Productos
class ProductoViewSet(viewsets.ModelViewSet):
    serializer_class = ProductoSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        tienda_id = self.request.query_params.get("tienda_id")
        if not tienda_id:
            return Producto.objects.none()
        return Producto.objects.filter(tienda_id=tienda_id)

    def destroy(self, request, *args, **kwargs):
        tienda_id = self.request.query_params.get("tienda_id")
        producto = get_object_or_404(Producto, id=kwargs["pk"], tienda_id=tienda_id)
        if DetalleVenta.objects.filter(producto=producto).exists():
            return Response({"error": "No se puede eliminar un producto con ventas asociadas."}, status=400)
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["patch"], url_path="actualizar-cantidad")
    def actualizar_cantidad(self, request, pk=None):
        tienda_id = request.data.get("tienda_id")
        if not tienda_id:
            return Response({"error": "Debe proporcionar el ID de la tienda."}, status=400)
        producto = get_object_or_404(Producto, id=pk, tienda_id=tienda_id)
        nueva_cantidad = request.data.get("cantidad")
        if nueva_cantidad is not None and isinstance(nueva_cantidad, int):
            producto.cantidad = nueva_cantidad
            producto.save()
            return Response({"mensaje": "Cantidad actualizada correctamente."})
        return Response({"error": "Debe proporcionar una cantidad válida."}, status=400)

    @action(detail=False, methods=['get'], url_path="disponibles")
    def productos_disponibles(self, request):
        tienda_id = request.query_params.get("tienda_id")
        if not tienda_id:
            return Producto.objects.none()
        productos = Producto.objects.filter(tienda_id=tienda_id, cantidad__gt=0)
        serializer = self.get_serializer(productos, many=True)
        return Response(serializer.data)


# Vista para Ventas
class VentaViewSet(viewsets.ModelViewSet):
    queryset = Venta.objects.all()
    serializer_class = VentaSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        usuario = self.request.user
        tienda = self.request.query_params.get("tienda")
        queryset = Venta.objects.filter(usuario=usuario)
        if tienda:
            queryset = queryset.filter(tienda_id=tienda)
        return queryset.order_by('-fecha')

    def create(self, request, *args, **kwargs):
        usuario = request.user
        tienda_id = _resolve_tienda_id(request)
        productos = request.data.get("productos")  # [{producto, cantidad}]

        if not tienda_id:
            return Response({"error": "Debe proporcionar la tienda o seleccionar una tienda activa."}, status=status.HTTP_400_BAD_REQUEST)

        tienda = get_object_or_404(Tienda, id=tienda_id)
        if not _usuario_tiene_acceso_tienda(usuario, tienda):
            return Response({"error": "No tiene permiso para registrar ventas en esta tienda."}, status=status.HTTP_403_FORBIDDEN)

        if not isinstance(productos, list) or not productos:
            return Response({"error": "Debe enviar una lista de productos válida."}, status=status.HTTP_400_BAD_REQUEST)

        # Verifica caja abierta para la tienda activa
        caja = Caja.objects.filter(tienda=tienda, estado='abierta').first()
        if not caja:
            return Response({"error": "No hay caja abierta para esta tienda."}, status=status.HTTP_400_BAD_REQUEST)

        detalles = []
        total = Decimal("0.00")

        with transaction.atomic():
            productos_ids = [item.get("producto") for item in productos]
            productos_por_id = {
                producto.id: producto
                for producto in Producto.objects.select_for_update().filter(id__in=productos_ids, tienda=tienda)
            }

            if len(productos_por_id) != len(set(productos_ids)):
                faltantes = sorted({str(producto_id) for producto_id in productos_ids if producto_id not in productos_por_id})
                return Response(
                    {"error": f"Hay productos inválidos o que no pertenecen a esta tienda: {', '.join(faltantes)}."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            for item in productos:
                producto_id = item.get("producto")
                if producto_id is None:
                    return Response({"error": "Cada producto debe incluir el ID del producto."}, status=status.HTTP_400_BAD_REQUEST)

                producto = productos_por_id[producto_id]
                try:
                    cantidad = int(item.get("cantidad", 0))
                except (TypeError, ValueError):
                    return Response({"error": f"Cantidad inválida para {producto.nombre}."}, status=status.HTTP_400_BAD_REQUEST)

                if cantidad <= 0:
                    return Response({"error": f"La cantidad de {producto.nombre} debe ser mayor que cero."}, status=status.HTTP_400_BAD_REQUEST)

                if producto.cantidad < cantidad:
                    return Response(
                        {"error": f"Stock insuficiente para {producto.nombre}"},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                subtotal = producto.precio * cantidad
                total += subtotal
                detalles.append({
                    "producto": producto,
                    "cantidad": cantidad,
                    "precio_unitario": producto.precio,
                    "subtotal": subtotal,
                })

            venta = Venta.objects.create(tienda=tienda, caja=caja, usuario=usuario, total=total)

            for detalle in detalles:
                producto = detalle["producto"]
                producto.cantidad -= detalle["cantidad"]
                producto.save(update_fields=["cantidad"])

                DetalleVenta.objects.create(
                    venta=venta,
                    producto=producto,
                    cantidad=detalle["cantidad"],
                    precio_unitario=detalle["precio_unitario"],
                    subtotal=detalle["subtotal"]
                )

        return Response(VentaSerializer(venta).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def total_hoy(self, request):
        hoy = now().date()
        ventas = Venta.objects.filter(usuario=request.user, fecha__date=hoy)
        total = sum(v.total for v in ventas)
        return Response({"fecha": str(hoy), "total_ventas": total})

# Vista para Detalles de Ventas
class DetalleVentaViewSet(viewsets.ModelViewSet):
    queryset = DetalleVenta.objects.all()
    serializer_class = DetalleVentaSerializer
    permission_classes = [permissions.IsAuthenticated]

# Vista para Gastos
class GastoViewSet(viewsets.ModelViewSet):
    serializer_class = GastoSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        tienda_id = self.request.query_params.get("tienda_id")
        if not tienda_id:
            return Gasto.objects.none()
        return Gasto.objects.filter(tienda_id=tienda_id)

    def perform_create(self, serializer):
        tienda_id = _resolve_tienda_id(self.request)
        if not tienda_id:
            raise serializers.ValidationError("Debe proporcionar el ID de la tienda.")
        tienda = get_object_or_404(Tienda, id=tienda_id)
        if not _usuario_tiene_acceso_tienda(self.request.user, tienda):
            raise serializers.ValidationError("No tiene permiso para registrar gastos en esta tienda.")
        caja = Caja.objects.filter(tienda=tienda, estado="abierta").first()
        if not caja:
            raise serializers.ValidationError("No hay una caja abierta en la tienda.")
        serializer.save(tienda=tienda, caja=caja, usuario=self.request.user)

    @action(detail=False, methods=['get'], url_path="por-categoria")
    def listar_por_categoria(self, request):
        tienda_id = request.query_params.get("tienda_id")
        if not tienda_id:
            return Response({"error": "Debe proporcionar el ID de la tienda."}, status=400)
        gastos = Gasto.objects.filter(tienda_id=tienda_id).values("categoria").annotate(total=models.Sum("monto"))
        return Response(gastos)


class CajaViewSet(viewsets.ModelViewSet):
    serializer_class = CajaSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        tienda_id = self.request.query_params.get("tienda_id")
        if not tienda_id:
            return Caja.objects.none()
        return Caja.objects.filter(tienda_id=tienda_id)

    def perform_create(self, serializer):
        tienda_id = _resolve_tienda_id(self.request)
        if not tienda_id:
            raise serializers.ValidationError("Debe proporcionar el ID de la tienda.")
        tienda = get_object_or_404(Tienda, id=tienda_id)
        if not _usuario_tiene_acceso_tienda(self.request.user, tienda):
            raise serializers.ValidationError("No tiene permiso para abrir caja en esta tienda.")
        if Caja.objects.filter(tienda=tienda, estado='abierta').exists():
            raise serializers.ValidationError("Ya hay una caja abierta para esta tienda.")
        serializer.save(usuario=self.request.user, tienda=tienda)

    @action(detail=True, methods=['post'])
    def cerrar(self, request, pk=None):
        try:
            caja = self.get_object()
            if caja.estado == 'cerrada':
                return Response({"error": "La caja ya está cerrada."}, status=status.HTTP_400_BAD_REQUEST)
            saldo_final = request.data.get('saldo_final')
            if saldo_final is None:
                return Response({"error": "Debe proporcionar el saldo final."}, status=status.HTTP_400_BAD_REQUEST)
            caja.cerrar_caja(saldo_final)
            return Response({"mensaje": "Caja cerrada con éxito."}, status=status.HTTP_200_OK)
        except Caja.DoesNotExist:
            return Response({"error": "Caja no encontrada."}, status=status.HTTP_404_NOT_FOUND)

