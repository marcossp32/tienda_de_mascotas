from flask import Flask, jsonify, request
from kafka import KafkaProducer, KafkaConsumer
from flask_sqlalchemy import SQLAlchemy
from threading import Thread, Event
from functools import wraps
from datetime import datetime

import json
import os
import uuid
import jwt
import sys


sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

app = Flask(__name__)

# Configuración de Flask y SQLAlchemy

## Las variables críticas se deberian añadri en un .env por eso la estructura de os.getenv pero como yo por simplicidad no lo implemento agrego el valor que tiene a la derecha.

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:12345@postgres-service.default.svc.cluster.local:5432/petstore")
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

KAFKA_BROKER = os.getenv("KAFKA_BROKER", "localhost:9092")
SECRET_KEY = os.getenv("SECRET_KEY", "supersecretkey")

# Creación de productor de kafka
producer = KafkaProducer(
    bootstrap_servers=KAFKA_BROKER,
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)


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


def consume_cart_items_request():
    """
    Función para consumir mensajes del tópico de Kafka `cart-items-requests`.

    Este consumidor se conecta al tópico `cart-items-requests` en el broker de Kafka 
    configurado. Procesa cada mensaje recibido extrayendo el `user_id` y el `token`, 
    simula una solicitud a un endpoint protegido (`/api/cart`) utilizando estos datos y 
    publica la respuesta en otro tópico de Kafka llamado `cart-responses`.

    Proceso:
    - Conecta al tópico `cart-items-requests`.
    - Extrae información del mensaje, como `user_id` y `token`.
    - Simula una solicitud HTTP al endpoint `/api/cart` utilizando el token recibido.
    - Si la solicitud es exitosa, publica los resultados en el tópico `cart-responses`.
    - Maneja posibles errores durante el consumo o procesamiento de mensajes.

    Args:
        None

    Returns:
        None
    """
    try:
        # Creación del consumidor de Kafka para el tópico `cart-items-requests`
        consumer = KafkaConsumer(
            "cart-items-requests",
            bootstrap_servers=KAFKA_BROKER,
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),
            group_id="cart-service",
            auto_offset_reset="latest"  # Procesar únicamente los mensajes más recientes
        )

        # Procesar cada mensaje del tópico
        for message in consumer:
            data = message.value
            user_id = data.get("user_id")
            token = data.get("token")

            # Crear encabezados de la solicitud simulada con el token JWT
            headers = {
                'Authorization': f'Bearer {token}'
            }

            # Simular una solicitud HTTP al endpoint `/api/cart`
            with app.test_request_context(f"/api/cart?user_id={user_id}", headers=headers):
                response = get_cart()  # Llamar al endpoint directamente
                status_code = response[1]  # Obtener el código de estado HTTP

                # Si la respuesta es exitosa, publicar los resultados en Kafka
                if status_code == 200:
                    cart_items = response[0].get_json()  # Obtener los datos de la respuesta
                    producer.send("cart-responses", cart_items)  # Publicar en el tópico `cart-responses`
                    producer.flush()
                else:
                    print(f"Error en el endpoint: {status_code}")  # Manejar errores en el endpoint

    except Exception as e:
        # Manejar errores durante el consumo o procesamiento de mensajes
        print(f"Error al procesar la solicitud de dirección: {e}")



# Iniciar consumidor en un hilo separado
Thread(target=consume_cart_items_request, daemon=True).start()


@app.route('/api/cart', methods=['GET'])
@token_required
def get_cart():
    """
    Endpoint para obtener el carrito actual de un usuario y publicar los detalles en Kafka.

    Este endpoint, protegido mediante el decorador `@token_required`, permite a un usuario autenticado
    obtener los detalles de su carrito de compras. También publica la respuesta en un tópico de Kafka
    llamado `cart-responses` para que otros servicios puedan consumir la información.

    Flujo:
    1. Extrae el `user_id` de los parámetros de la solicitud.
    2. Verifica que el `user_id` esté presente. Si no, devuelve un error 400.
    3. Consulta la base de datos para obtener el carrito asociado al usuario.
    4. Si no se encuentra un carrito, publica un mensaje en Kafka indicando que no se encontró y devuelve un error 404.
    5. Si se encuentra un carrito, consulta los ítems asociados al carrito y construye la respuesta.
    6. Publica la respuesta del carrito en Kafka y la devuelve al cliente.

    Args:
        None

    Returns:
        Response: Respuesta en formato JSON con los detalles del carrito o un mensaje de error.
    """
    try:
        # Obtener el ID del usuario autenticado
        user_id = request.args.get('user_id')  # En producción, el ID se obtendría del token JWT

        # Validar que el ID de usuario esté presente
        if not user_id:
            return jsonify({"message": "El campo 'user_id' es obligatorio."}), 400

        # Consultar el carrito del usuario en la base de datos
        cart_query = """
        SELECT id, total_amount, created_at, updated_at
        FROM carts
        WHERE user_id = :user_id
        """
        cart = db.session.execute(cart_query, {"user_id": user_id}).fetchone()

        # Si no se encuentra un carrito, enviar respuesta de error a Kafka y devolver 404
        if not cart:
            response = {"message": "Carrito no encontrado."}
            producer.send('cart-responses', {"user_id": user_id, "response": response})
            producer.flush()
            return jsonify(response), 404

        # Extraer el ID del carrito
        cart_id = cart["id"]

        # Consultar los ítems del carrito asociados al usuario
        items_query = """
        SELECT ci.id AS cart_item_id, ci.quantity, ci.price, 
               p.id AS product_id, p.name AS product_name, p.images AS product_images
        FROM cart_items ci
        JOIN products p ON ci.product_id = p.id
        WHERE ci.cart_id = :cart_id
        """
        items = db.session.execute(items_query, {"cart_id": cart_id}).fetchall()

        # Construir una lista de ítems del carrito
        cart_items = [{
            "cart_item_id": str(item["cart_item_id"]),
            "product_id": str(item["product_id"]),
            "product_name": item["product_name"],
            "product_images": item["product_images"],
            "quantity": item["quantity"],
            "price": item["price"]
        } for item in items]

        # Construir la respuesta completa con los detalles del carrito
        response = {
            "cart_id": str(cart_id),
            "total_amount": cart["total_amount"],
            "created_at": cart["created_at"].isoformat(),
            "updated_at": cart["updated_at"].isoformat(),
            "items": cart_items
        }

        # Publicar la respuesta en Kafka
        kafka_message = {"user_id": user_id, "response": response}
        producer.send('cart-responses', kafka_message)
        producer.flush()

        # Devolver la respuesta al cliente
        return jsonify(response), 200

    except Exception as e:
        # Manejo de errores durante la consulta o procesamiento
        error_message = f"Error al obtener el carrito: {str(e)}"
        producer.send('cart-responses', {"user_id": user_id, "response": {"message": error_message}})
        producer.flush()
        return jsonify({"message": error_message}), 500




# Diccionarios y locks
product_availability_response = []
product_availability_event = Event()

def consume_availability_responses():
    """
    Función para consumir respuestas de disponibilidad de productos desde Kafka.

    Este consumidor se conecta al tópico `product-availability-responses` en el broker de Kafka configurado.
    Cuando se recibe un mensaje, se extraen los datos de la respuesta y se añaden a una lista global
    `product_availability_response`. Una vez procesado el mensaje, se activa el evento 
    `product_availability_event` para notificar que la respuesta está lista.

    Flujo:
    1. Conecta al tópico `product-availability-responses` en Kafka.
    2. Procesa el primer mensaje recibido, lo guarda en la lista compartida `product_availability_response`.
    3. Activa el evento `product_availability_event` para desbloquear cualquier proceso dependiente.

    Args:
        None

    Returns:
        None
    """
    # Crear un consumidor para el tópico `product-availability-responses`
    consumer = KafkaConsumer(
        'product-availability-responses',  # Tópico que contiene las respuestas de disponibilidad
        bootstrap_servers=KAFKA_BROKER,   # Dirección del broker de Kafka
        value_deserializer=lambda x: json.loads(x.decode('utf-8')),  # Deserializar los mensajes en formato JSON
        group_id='cart-service',          # Grupo de consumidores para gestionar el procesamiento
        enable_auto_commit=True,          # Confirmar automáticamente los mensajes procesados
        auto_offset_reset='latest'        # Procesar únicamente los mensajes más recientes
    )

    # Procesar los mensajes recibidos
    for message in consumer:
        data = message.value  # Extraer los datos del mensaje
        print(data)
        product_availability_response.append(data)  # Guardar los datos en la lista compartida
        product_availability_event.set()  # Activar el evento para notificar que hay una respuesta
        break  # Salir del bucle tras procesar el primer mensaje

# Iniciar el consumidor en un hilo separado
Thread(target=consume_availability_responses, daemon=True).start()


@app.route('/api/cart/items', methods=['POST'])
@token_required
def add_to_cart():
    """
    Endpoint para añadir un producto al carrito de compras de un usuario.

    Este endpoint permite a un usuario autenticado añadir un producto a su carrito. 
    Publica una solicitud en Kafka para verificar la disponibilidad del producto y, 
    si está disponible, lo añade al carrito. Si no está disponible o ocurre algún error, 
    devuelve un mensaje de error al cliente.

    Flujo:
    1. Valida los datos de entrada (`product_id`, `user_id`).
    2. Publica una solicitud en Kafka para verificar la disponibilidad del producto.
    3. Espera una respuesta de disponibilidad desde Kafka.
    4. Si el producto está disponible:
        - Crea un nuevo carrito si el usuario no tiene uno.
        - Añade el producto al carrito.
        - Actualiza el total del carrito.
    5. Devuelve un mensaje de éxito o maneja los errores según corresponda.

    Args:
        None

    Returns:
        Response: Respuesta en formato JSON con un mensaje de éxito o error.
    """
    try:
        # Obtener datos de la solicitud
        data = request.get_json()
        product_id = data.get('product_id')
        quantity = data.get('quantity', 1)
        user_id = data.get('user_id')
        token = request.headers.get('Authorization').split(" ")[1]

        # Validar los datos de entrada
        if not product_id or not user_id:
            return jsonify({"message": "Los campos 'product_id' y 'user_id' son obligatorios."}), 400

        # Publicar solicitud de disponibilidad en Kafka
        availability_request = {"product_id": product_id, "quantity": quantity, "token": token}
        producer.send('product-availability-requests', availability_request)
        producer.flush()

        # Esperar respuesta de disponibilidad
        if not product_availability_event.wait(timeout=20):
            return jsonify({"message": "Timeout al obtener la respuesta de disponibilidad."}), 500

        # Verificar si hay una respuesta disponible
        if not product_availability_response:
            return jsonify({"message": "No se recibió respuesta de disponibilidad."}), 404

        response = product_availability_response[0]

        # Si el producto no está disponible, devolver un error
        if not response.get('available', False):
            return jsonify({"message": "El producto no está disponible."}), 400

        # Lógica para añadir el producto al carrito
        with db.session.begin():
            # Buscar carrito del usuario
            cart = db.session.execute(
                "SELECT id, total_amount FROM carts WHERE user_id = :user_id",
                {"user_id": user_id}
            ).fetchone()

            # Crear un nuevo carrito si no existe
            if not cart:
                cart_id = str(uuid.uuid4())
                db.session.execute(
                    """
                    INSERT INTO carts (id, user_id, total_amount, created_at, updated_at)
                    VALUES (:id, :user_id, 0, :created_at, :updated_at)
                    """,
                    {"id": cart_id, "user_id": user_id, "created_at": datetime.utcnow(), "updated_at": datetime.utcnow()}
                )
                cart_total = 0
            else:
                cart_id = cart['id']
                cart_total = cart['total_amount']

            # Añadir producto al carrito
            price = response.get('price', 0)
            db.session.execute(
                """
                INSERT INTO cart_items (id, cart_id, product_id, quantity, price)
                VALUES (:id, :cart_id, :product_id, :quantity, :price)
                """,
                {
                    "id": str(uuid.uuid4()),
                    "cart_id": cart_id,
                    "product_id": product_id,
                    "quantity": quantity,
                    "price": price
                }
            )

            # Actualizar el total del carrito
            new_total = cart_total + (price * quantity)
            db.session.execute(
                """
                UPDATE carts SET total_amount = :total_amount, updated_at = :updated_at
                WHERE id = :cart_id
                """,
                {"total_amount": new_total, "updated_at": datetime.utcnow(), "cart_id": cart_id}
            )

        # Respuesta de éxito
        return jsonify({"message": "Producto añadido al carrito exitosamente."}), 200

    except Exception as e:
        # Manejar errores
        return jsonify({"message": f"Error interno: {str(e)}"}), 500




if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000,debug=True)
