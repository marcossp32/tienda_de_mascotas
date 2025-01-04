from flask import Flask, jsonify, request
from kafka import KafkaProducer, KafkaConsumer
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from functools import wraps

import threading
import json
import uuid
import os
import sys
import jwt

# Configurar la salida estándar para manejar el buffering correctamente
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# Configuración de Flask
app = Flask(__name__)

# Configuración de la base de datos y SQLAlchemy
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql://postgres:12345@postgres-service.default.svc.cluster.local:5432/petstore"
)
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Configuración de Kafka
KAFKA_BROKER = os.getenv("KAFKA_BROKER", "localhost:9092")
producer = KafkaProducer(
    bootstrap_servers=KAFKA_BROKER,
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

# Clave secreta para JWT
SECRET_KEY = os.getenv("SECRET_KEY", "supersecretkey")

def token_required(f):
    """
    Decorador para proteger rutas mediante autenticación basada en tokens JWT.
    
    Este decorador asegura que las rutas protegidas solo puedan ser accedidas por usuarios 
    que envíen un token JWT válido en el encabezado `Authorization`. Si el token no es 
    válido o está ausente, se devuelve una respuesta con un código de estado HTTP apropiado.
    
    Args:
        f (function): La función que será decorada.

    Returns:
        function: La función decorada con validación de token.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None

        # Verificar si el token está presente en el encabezado Authorization
        if 'Authorization' in request.headers:
            try:
                # Extraer el encabezado Authorization y separar el token después de "Bearer"
                auth_header = request.headers['Authorization']
                token = auth_header.split(" ")[1]  
            except IndexError:
                # Si el formato del token es incorrecto
                return jsonify({'message': 'Formato del token inválido'}), 401

        # Si no hay token en el encabezado
        if not token:
            return jsonify({'message': 'Token faltante'}), 401

        try:
            # Decodificar el token utilizando la clave secreta y el algoritmo HS256
            data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            # Asignar el ID del usuario (user_id) al objeto request para su uso posterior
            request.user_id = data['user_id']
        except jwt.ExpiredSignatureError:
            # Si el token ha expirado
            return jsonify({'message': 'Token expirado'}), 401
        except jwt.InvalidTokenError:
            # Si el token no es válido
            return jsonify({'message': 'Token inválido'}), 401

        # Si el token es válido, proceder a ejecutar la función original
        return f(*args, **kwargs)

    return decorated

# Variables globales y eventos para respuestas de Kafka
cart_items_response = []
cart_event = threading.Event()
address_response = []
address_event = threading.Event()

def consume_cart_items_response():
    """
    Consumidor para el tópico de Kafka `cart-responses`.

    Este consumidor escucha las respuestas de los ítems del carrito en el tópico `cart-responses`.
    Cuando se recibe un mensaje, los datos se almacenan en una lista compartida y se activa un evento
    para notificar que hay una respuesta disponible.

    Args:
        None

    Returns:
        None
    """
    consumer = KafkaConsumer(
        "cart-responses",
        bootstrap_servers=KAFKA_BROKER,
        value_deserializer=lambda x: json.loads(x.decode('utf-8')),
        group_id=f"order-service-{os.getpid()}",
        auto_offset_reset="latest",
    )
    print("Cart consumer iniciado")
    for message in consumer:
        data = message.value
        cart_items_response.append(data)
        cart_event.set()
        break

# Inicia el consumidor de ítems del carrito en un hilo separado
threading.Thread(target=consume_cart_items_response, daemon=True).start()

def consume_address_response():
    """
    Consumidor para el tópico de Kafka `address-responses`.

    Este consumidor escucha las respuestas de direcciones en el tópico `address-responses`.
    Cuando se recibe un mensaje, los datos se almacenan en una lista compartida y se activa un evento
    para notificar que hay una respuesta disponible.

    Args:
        None

    Returns:
        None
    """
    consumer = KafkaConsumer(
        "address-responses",
        bootstrap_servers=KAFKA_BROKER,
        value_deserializer=lambda x: json.loads(x.decode('utf-8')),
        group_id=f"order-service-{os.getpid()}",
        auto_offset_reset="latest",
    )
    print("Address consumer iniciado")
    for message in consumer:
        data = message.value
        address_response.append(data)
        address_event.set()
        break

# Inicia el consumidor de direcciones en un hilo separado
threading.Thread(target=consume_address_response, daemon=True).start()

# Endpoint para crear un pedido
@app.route('/api/orders', methods=['POST'])
@token_required
def create_order():
    """
    Endpoint para crear un nuevo pedido.

    Este endpoint permite a un usuario autenticado crear un pedido. Solicita la dirección del usuario
    y los ítems del carrito a través de Kafka, calcula el total del pedido, lo almacena en la base de datos
    y publica actualizaciones del inventario en Kafka.

    Args:
        None

    Returns:
        Response: JSON con el ID del pedido creado o un mensaje de error.
    """
    try:
        data = request.get_json()
        user_id = data.get("user_id")
        payment_method = data.get("payment_method")
        token = request.headers.get('Authorization').split(" ")[1]  # Extraer el token

        # Validar campos obligatorios
        if not user_id or not payment_method:
            return jsonify({"message": "Faltan campos obligatorios (user_id, payment_method)."}), 400

        # Publicar solicitud en Kafka para dirección e ítems del carrito
        request_data = {
            "user_id": user_id,
            "token": token  
        }

        producer.send("address-requests", request_data)
        producer.flush()

        producer.send("cart-items-requests", request_data)
        producer.flush()

        # Esperar respuesta de dirección
        if not address_event.wait(timeout=20):
            return jsonify({"message": "Timeout al obtener la dirección del usuario."}), 500

        if not address_response:
            return jsonify({"message": "No se encontró dirección para el usuario."}), 404

        shipping_address = address_response[0]

        # Esperar respuesta del carrito
        if not cart_event.wait(timeout=20):
            return jsonify({"message": "Timeout al obtener ítems del carrito."}), 500

        cart_response = cart_items_response[0]

        if not isinstance(cart_response, dict) or "response" not in cart_response:
            return jsonify({"message": "Formato inválido del mensaje del carrito."}), 500

        cart_data = cart_response["response"]

        if not isinstance(cart_data, dict) or "items" not in cart_data or not cart_data["items"]:
            return jsonify({"message": "No se encontraron ítems en el carrito."}), 404

        cart_items = cart_data["items"]

        # Crear pedido
        total_amount = sum(item["quantity"] * item["price"] for item in cart_items)
        order_id = str(uuid.uuid4())
        created_at = datetime.utcnow()
        updated_at = datetime.utcnow()

        # Insertar el pedido
        order_query = """
            INSERT INTO orders (id, user_id, total_amount, shipping_address, payment_method, payment_status, order_status, created_at, updated_at)
            VALUES (:order_id, :user_id, :total_amount, :shipping_address, :payment_method, :payment_status, :order_status, :created_at, :updated_at)
        """
        order_params = {
            'order_id': order_id,
            'user_id': user_id,
            'total_amount': total_amount,
            'shipping_address': json.dumps(shipping_address),
            'payment_method': payment_method,
            'payment_status': "Pending",
            'order_status': "Pending",
            'created_at': created_at,
            'updated_at': updated_at,
        }

        try:
            db.session.execute(order_query, order_params)

            # Insertar los ítems del pedido
            order_item_query = """
                INSERT INTO order_items (id, order_id, product_id, quantity, price)
                VALUES (:item_id, :order_id, :product_id, :quantity, :price)
            """
            for item in cart_items:
                order_item_params = {
                    'item_id': str(uuid.uuid4()),
                    'order_id': order_id,
                    'product_id': item["product_id"],
                    'quantity': item["quantity"],
                    'price': item["price"],
                }
                db.session.execute(order_item_query, order_item_params)

            # Confirmar la transacción
            db.session.commit()
            print("Pedido y sus ítems guardados en la base de datos.")
        except Exception as e:
            db.session.rollback()
            print(f"Error al guardar el pedido: {e}")
            return jsonify({"message": "Error al crear el pedido en la base de datos."}), 500

        # Publicar el pedido en Kafka para registro
        print("Pedido confirmado")

        # Actualizar inventario
        for item in cart_items:
            inventory_update = {"product_id": item["product_id"], "quantity": -item["quantity"], "token": token}
            producer.send("inventory-updates", inventory_update)
        producer.flush()
        print("Solicitudes de actualización de inventario enviadas a Kafka.")

        return jsonify({"message": "Pedido creado exitosamente.", "order_id": order_id}), 201

    except Exception as e:
        error_message = f"Error al crear pedido: {str(e)}"
        print(error_message)
        return jsonify({"message": error_message}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
