from django.shortcuts import get_object_or_404
from rest_framework import serializers
from django.contrib.auth import get_user_model, authenticate
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from dj_rest_auth.registration.serializers import RegisterSerializer
from .models import Usuario, Tienda, Empleado, Producto, Venta, DetalleVenta, Gasto, Caja

# Obtener el modelo de usuario personalizado
#Usuario = get_user_model()

# Serializador para Usuario
class UsuarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Usuario
        fields = ['id', 'username', 'email', 'telefono', 'rol']
        read_only_fields = ['rol']


class VendedorRegisterSerializer(RegisterSerializer):
    """Registro publico: siempre crea usuarios con rol vendedor."""

    def validate_email(self, email):
        email = (email or '').strip().lower()
        if not email:
            raise serializers.ValidationError("El correo es obligatorio.")

        if Usuario.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("Ya existe una cuenta con este correo.")

        return email

    def custom_signup(self, request, user):
        user.rol = Usuario.Rol.VENDEDOR
        user.is_staff = False
        user.is_superuser = False
        user.save(update_fields=['rol', 'is_staff', 'is_superuser'])

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['username'] = user.username
        token['rol'] = user.rol
        return token

    def validate(self, attrs):
        login_input = (attrs.get('username') or '').strip()
        password = attrs.get('password')
        request = self.context.get('request')

        if not login_input or not password:
            raise serializers.ValidationError("Debe enviar usuario/email y contraseña.")

        # 1) Intenta autenticación normal por username.
        user = authenticate(request=request, username=login_input, password=password)

        # 2) Si falla, intenta por email y usa el username real del usuario encontrado.
        if user is None:
            usuarios = Usuario.objects.filter(email__iexact=login_input)
            if usuarios.count() == 1:
                user = authenticate(
                    request=request,
                    username=usuarios.first().username,
                    password=password,
                )
            elif usuarios.count() > 1:
                raise serializers.ValidationError(
                    "Hay múltiples cuentas con ese correo. Inicie sesión con usuario."
                )

        if user is None:
            raise serializers.ValidationError("Credenciales inválidas.")

        refresh = self.get_token(user)
        return {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'rol': user.rol,
            },
        }
    
# Serializador para Tienda
class TiendaSerializer(serializers.ModelSerializer):
    propietario = UsuarioSerializer(read_only=True)
    empleados = serializers.SerializerMethodField()  # Agrega una función para obtener empleados específicos

    class Meta:
        model = Tienda
        fields = ['id', 'nombre', 'telefono', 'direccion', 'propietario', 'empleados']

    def get_empleados(self, obj):
        """Obtiene los empleados pertenecientes a la tienda específica"""
        empleados = obj.empleados.all()  # Filtra empleados de esta tienda
        return [{"id": emp.id, "nombre": emp.usuario.username} for emp in empleados]

    def create(self, validated_data):
        """
        Sobrescribe el método create para asignar automáticamente el propietario de la tienda.
        """
        request = self.context.get('request')
        if request and hasattr(request, "user"):
            validated_data['propietario'] = request.user  # Asignar el usuario autenticado como propietario
        return Tienda.objects.create(**validated_data)
    
    
    def update(self, instance, validated_data):
        instance.nombre = validated_data.get('nombre', instance.nombre)
        instance.direccion = validated_data.get('direccion', instance.direccion)
        instance.telefono = validated_data.get('telefono', instance.telefono)

        instance.save()
        return instance

# Serializador para Empleado
class EmpleadoSerializer(serializers.ModelSerializer):
    tienda = serializers.PrimaryKeyRelatedField(queryset=Tienda.objects.all())

    class Meta:
        model = Empleado
        fields = ['id', 'usuario', 'tienda']

# Serializador para Producto
class ProductoSerializer(serializers.ModelSerializer):
    tienda = serializers.PrimaryKeyRelatedField(read_only=True)
    tienda_id = serializers.IntegerField(write_only=True, required=False)

    class Meta:
        model = Producto
        fields = ["id", "tienda", "tienda_id", "nombre", "categoria", "precio", "cantidad", "codigo_barras"]

    def create(self, validated_data):
        tienda_id = validated_data.pop("tienda_id", None)

        if not tienda_id:
            request = self.context.get("request")
            if request:
                tienda_id = request.data.get("tienda_id") or request.session.get("tienda_id")

        if not tienda_id:
            raise serializers.ValidationError({
                "tienda_id": "Debe proporcionar el ID de la tienda o seleccionar una tienda activa."
            })

        try:
            tienda_id = int(tienda_id)
        except (TypeError, ValueError):
            raise serializers.ValidationError({"tienda_id": "El ID de la tienda es inválido."})

        tienda = Tienda.objects.filter(id=tienda_id).first()
        if not tienda:
            raise serializers.ValidationError({
                "tienda_id": f"La tienda con id {tienda_id} no existe."
            })
        return Producto.objects.create(tienda=tienda, **validated_data)

    

# Serializador para Detalle de Venta
class DetalleVentaSerializer(serializers.ModelSerializer):
    producto = ProductoSerializer(read_only=True)

    class Meta:
        model = DetalleVenta
        fields = ['id', 'venta', 'producto', 'cantidad', 'subtotal']

# Serializador para Venta
class VentaSerializer(serializers.ModelSerializer):
    detalles = DetalleVentaSerializer(many=True, read_only=True)
    vendedor = UsuarioSerializer(source='usuario', read_only=True)

    class Meta:
        model = Venta
        fields = ['id', 'tienda', 'vendedor', 'fecha', 'total', 'detalles']

# Serializador para Gasto
class GastoSerializer(serializers.ModelSerializer):
    """
    Serializador para gestionar gastos.
    """

    tienda_id = serializers.IntegerField(write_only=True, required=False)

    class Meta:
        model = Gasto
        fields = ["id", "tienda", "tienda_id", "caja", "usuario", "fecha", "descripcion", "monto", "categoria"]
        read_only_fields = ["id", "fecha", "usuario", "caja", "tienda"]  # La tienda se asignará automáticamente

    def _resolve_tienda_id(self):
        request = self.context.get("request")
        if not request:
            return None
        return (
            request.data.get("tienda_id")
            or request.data.get("tienda")
            or request.session.get("tienda_id")
        )

    def validate(self, data):
        """
        Valida que haya una caja abierta en la tienda activa antes de registrar el gasto.
        """
        request = self.context.get("request")
        if not request:
            raise serializers.ValidationError("No se pudo obtener el usuario de la solicitud.")

        tienda_id = self._resolve_tienda_id()
        if not tienda_id:
            raise serializers.ValidationError("No hay una tienda activa seleccionada.")

        tienda = get_object_or_404(Tienda, id=tienda_id)
        caja_abierta = Caja.objects.filter(tienda=tienda, estado="abierta").first()
        if not caja_abierta:
            raise serializers.ValidationError("No hay una caja abierta en la tienda para registrar el gasto.")

        data["usuario"] = request.user
        data["tienda"] = tienda  # Asigna automáticamente la tienda activa
        data["caja"] = caja_abierta
        return data


class CajaSerializer(serializers.ModelSerializer):
    tienda_id = serializers.IntegerField(write_only=True, required=False)

    class Meta:
        model = Caja
        fields = ['id', 'usuario', 'tienda_id', 'turno', 'saldo_inicial', 'saldo_final', 'fecha_apertura', 'fecha_cierre', 'estado']
        read_only_fields = ['id', 'usuario', 'fecha_apertura', 'fecha_cierre', 'estado']

    def _resolve_tienda_id(self):
        request = self.context.get('request')
        if not request:
            return None
        return (
            request.data.get('tienda_id')
            or request.data.get('tienda')
            or request.session.get('tienda_id')
        )

    def validate(self, data):
        """
        Validar que no haya otra caja abierta en la tienda activa.
        """
        tienda_id = self._resolve_tienda_id()
        
        if not tienda_id:
            raise serializers.ValidationError("No hay una tienda activa seleccionada.")

        # Verificar si ya existe una caja abierta en la tienda activa
        if Caja.objects.filter(tienda_id=tienda_id, estado='abierta').exists():
            raise serializers.ValidationError("Ya hay una caja abierta en la tienda activa.")
        
        return data

    def create(self, validated_data):
        """
        Asigna la tienda activa y el usuario autenticado al crear la caja.
        """
        request = self.context.get('request')
        tienda_id = self._resolve_tienda_id()
        
        if not tienda_id:
            raise serializers.ValidationError("No hay una tienda activa seleccionada.")
        
        validated_data['tienda'] = get_object_or_404(Tienda, id=tienda_id)
        if request and hasattr(request, 'user'):
            validated_data['usuario'] = request.user
        
        return super().create(validated_data)
