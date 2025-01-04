from flask_sqlalchemy import SQLAlchemy
from flask import Flask, request, jsonify
from kafka import KafkaConsumer, KafkaProducer
from threading import Lock, Event
from datetime import datetime
from functools import wraps

import json
import os
import threading
import random
import sys
import uuid
import jwt

# Configurar la salida estándar para manejar el buffering correctamente
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# Configuración de Flask
app = Flask(__name__)

# Configuración de la base de datos
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:12345@postgres-service.default.svc.cluster.local:5432/petstore")
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


def consume_availability_requests():
    """
    Función para consumir solicitudes de disponibilidad de productos desde un tópico de Kafka.

    Esta función escucha mensajes en el tópico `product-availability-requests` de Kafka. 
    Cada mensaje contiene un `product_id`, una cantidad solicitada (`quantity`) y un token de autenticación (`token`).
    Luego:
    - Simula una solicitud al endpoint `/api/products` para obtener información del producto.
    - Evalúa si el producto tiene suficiente stock para satisfacer la cantidad solicitada.
    - Publica una respuesta en el tópico `product-availability-responses` indicando si el producto está disponible,
      el stock actual y el precio.

    Args:
        None

    Returns:
        None
    """
    try:
        # Inicializar el consumidor de Kafka para el tópico `product-availability-requests`
        consumer = KafkaConsumer(
            'product-availability-requests',  # Nombre del tópico
            bootstrap_servers=KAFKA_BROKER,  # Dirección del broker de Kafka
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),  # Deserialización del mensaje JSON
            group_id=f'product-service-{random.randint(1, 100000)}',  # Grupo de consumidores único para evitar conflictos
            auto_offset_reset='latest'  # Procesar únicamente los mensajes más recientes
        )
        print("Iniciando consumo del tópico 'product-availability-requests'")

        # Iterar sobre los mensajes recibidos
        for message in consumer:
            data = message.value  # Obtener el contenido del mensaje
            product_id = data.get('product_id')  # ID del producto solicitado
            quantity = data.get('quantity', 1)  # Cantidad solicitada (por defecto 1)
            token = data.get("token")  # Token de autenticación JWT

            # Crear encabezados para simular la solicitud HTTP
            headers = {
                'Authorization': f'Bearer {token}'
            }

            # Simular una solicitud al endpoint `/api/products` con el ID del producto y encabezados
            with app.test_request_context(f"/api/products?q={product_id}", headers=headers):
                try:
                    response = list_products()  # Llamar al endpoint de productos

                    # Verificar si la respuesta es una tupla (contenido y código de estado)
                    if isinstance(response, tuple):
                        response_data, status_code = response
                    else:
                        response_data = response
                        status_code = 200  # Si no hay código de estado, asumir que es exitoso

                    # Procesar la respuesta si el estado HTTP es 200
                    if status_code == 200:
                        products = response_data.get_json().get('products', [])  # Obtener productos de la respuesta
                        print(f"Productos devueltos: {products}")  # Depuración
                        
                        # Buscar el producto solicitado por su ID
                        product = next((p for p in products if str(p['id']) == str(product_id)), None)

                        # Determinar disponibilidad y datos del producto
                        if product:
                            print(f"Producto encontrado: {product}")  # Depuración
                            stock = product.get('stock', 0)  # Obtener el stock actual
                            price = product.get('price', 0)  # Obtener el precio
                            available = stock >= quantity  # Evaluar si hay suficiente stock
                        else:
                            print(f"Producto no encontrado con ID: {product_id}")  # Depuración
                            stock = 0
                            price = 0
                            available = False

                        # Construir la respuesta para Kafka
                        kafka_response = {
                            "product_id": product_id,
                            "available": available,
                            "stock": stock,
                            "price": price
                        }
                        # Publicar la respuesta en el tópico `product-availability-responses`
                        producer.send('product-availability-responses', kafka_response)
                        producer.flush()
                        print(f"Respuesta de disponibilidad enviada: {kafka_response}")
                    else:
                        # Manejar errores en la solicitud al endpoint de productos
                        print(f"Error al consultar productos: {status_code}")
                except Exception as e:
                    # Manejar excepciones durante el procesamiento del mensaje
                    print(f"Error al procesar disponibilidad para producto {product_id}: {str(e)}")
    except Exception as e:
        # Manejar errores globales en el consumidor de Kafka
        print(f"Error en el consumidor de Kafka para 'product-availability-requests': {e}")



def consume_search_requests():
    """
    Función para consumir solicitudes de búsqueda desde un tópico de Kafka.

    Esta función escucha mensajes en el tópico `search-requests` de Kafka. 
    Cada mensaje contiene un término de búsqueda (`query`) y un token de autenticación (`token`).
    Luego:
    - Simula una solicitud al endpoint `/api/products` para buscar productos relacionados con el término.
    - Publica una respuesta en el tópico `products-responses` con los productos encontrados.

    Args:
        None

    Returns:
        None
    """
    try:
        print("Intentando inicializar el consumidor de Kafka...")

        # Inicializar el consumidor de Kafka para el tópico `search-requests`
        consumer = KafkaConsumer(
            'search-requests',  # Nombre del tópico
            bootstrap_servers=KAFKA_BROKER,  # Dirección del broker de Kafka
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),  # Deserializador de mensajes JSON
            group_id=f"product-service-{random.randint(1, 100000)}",  # Grupo de consumidores único
            auto_offset_reset='latest'  # Procesar solo los mensajes más recientes
        )
        print("Iniciando consumo del tópico 'search-requests'")

        # Iterar sobre los mensajes recibidos
        for message in consumer:
            data = message.value  # Obtener el contenido del mensaje
            query = data.get('query', '')  # Término de búsqueda (por defecto vacío)
            token = data.get("token")  # Token de autenticación JWT

            # Crear encabezados para simular la solicitud HTTP
            headers = {
                'Authorization': f'Bearer {token}'
            }

            # Simular una solicitud al endpoint `/api/products` con el término de búsqueda
            with app.test_request_context(f"/api/products?q={query}", headers=headers):
                try:
                    # Llamar directamente al endpoint de búsqueda de productos
                    response = list_products()
                    status_code = response[1]  # Obtener el código de estado HTTP

                    # Si la respuesta es exitosa (HTTP 200)
                    if status_code == 200:
                        products = response[0].get_json()['products']  # Extraer productos de la respuesta
                        
                        # Publicar los productos encontrados en el tópico `products-responses`
                        producer.send('products-responses', {'type': 'product', 'data': products})
                        producer.flush()
                        print(f"Respuesta enviada a Kafka: {products}")
                    else:
                        # Manejar errores en la solicitud al endpoint de productos
                        print(f"Error al consultar productos: {status_code}")

                except Exception as e:
                    # Manejar excepciones durante el procesamiento del mensaje
                    print(f"Error al procesar búsqueda para query '{query}': {str(e)}")
    except Exception as e:
        # Manejar errores globales en el consumidor de Kafka
        print(f"Error en el consumidor de Kafka para 'search-requests': {e}")



def consume_inventory_updates():
    """
    Consumidor de Kafka para actualizaciones de inventario.

    Este consumidor escucha mensajes en el tópico `inventory-updates` para manejar cambios en el inventario
    de productos. Cada mensaje contiene:
    - `product_id`: El identificador único del producto.
    - `quantity`: El cambio en la cantidad del inventario (puede ser positivo o negativo).

    Flujo:
    1. Escucha el mensaje del tópico `inventory-updates`.
    2. Consulta el inventario actual del producto en la base de datos.
    3. Calcula el nuevo inventario aplicando el cambio.
    4. Actualiza el inventario en la base de datos, asegurando que no sea negativo.
    5. Maneja errores durante el proceso, como productos no encontrados o excepciones de base de datos.

    Args:
        None

    Returns:
        None
    """
    # Inicializar el consumidor de Kafka para el tópico `inventory-updates`
    consumer = KafkaConsumer(
        'inventory-updates',  # Nombre del tópico
        bootstrap_servers=KAFKA_BROKER,  # Dirección del broker de Kafka
        value_deserializer=lambda x: json.loads(x.decode('utf-8')),  # Deserializador de mensajes JSON
        group_id=f'product-service-{random.randint(1, 100000)}',  # Grupo de consumidores único
        auto_offset_reset='latest'  # Procesar solo los mensajes más recientes
    )
    print("Iniciando consumo del tópico 'inventory-updates'")

    # Procesar los mensajes recibidos
    for message in consumer:
        data = message.value  # Obtener el contenido del mensaje
        product_id = data.get('product_id')  # ID del producto
        quantity_change = data.get('quantity', 0)  # Cambio en la cantidad del inventario
        print(f"Actualización de inventario recibida para producto {product_id}, cambio en cantidad: {quantity_change}")

        # Contexto de la aplicación para interactuar con la base de datos
        with app.app_context():
            try:
                # Consultar el inventario actual del producto
                query = "SELECT stock FROM products WHERE id = :product_id"
                result = db.session.execute(query, {'product_id': product_id}).fetchone()

                if result:
                    current_stock = result['stock']  # Inventario actual
                    new_stock = current_stock + quantity_change  # Calcular el nuevo inventario

                    # Validar que el inventario no sea negativo
                    if new_stock < 0:
                        print(f"Error: El inventario no puede ser negativo para producto {product_id}")
                        continue

                    # Actualizar el inventario en la base de datos
                    update_query = """
                    UPDATE products 
                    SET stock = :new_stock, updated_at = :updated_at 
                    WHERE id = :product_id
                    """
                    db.session.execute(update_query, {
                        'new_stock': new_stock,
                        'updated_at': datetime.utcnow(),
                        'product_id': product_id
                    })
                    db.session.commit()  # Confirmar la transacción
                    print(f"Inventario actualizado para producto {product_id}: {new_stock}")
                else:
                    # Manejar el caso de producto no encontrado
                    print(f"Producto {product_id} no encontrado.")
            except Exception as e:
                # Manejar errores durante la actualización
                print(f"Error al actualizar inventario para producto {product_id}: {str(e)}")


# Iniciar consumidores en hilos separados
threading.Thread(target=consume_search_requests, daemon=True).start()  # Consumidor de búsquedas
threading.Thread(target=consume_availability_requests, daemon=True).start()  # Consumidor de disponibilidad
threading.Thread(target=consume_inventory_updates, daemon=True).start()  # Consumidor de inventario



@app.route('/api/products', methods=['GET'])
@token_required
def list_products():
    """
    Endpoint para listar productos.

    Este endpoint permite a los usuarios autenticados buscar y filtrar productos según varios criterios. 
    Los resultados incluyen información detallada de los productos y pueden filtrarse por:
    - Nombre del producto (`q`).
    - Tipo de animal (`animal_type`).
    - Etiquetas (`tags`).

    Flujo:
    1. Obtiene los parámetros de consulta desde la solicitud HTTP.
    2. Construye dinámicamente una consulta SQL basada en los filtros proporcionados.
    3. Ejecuta la consulta y procesa los resultados en un formato JSON para la respuesta.
    4. Maneja errores durante el proceso y devuelve mensajes descriptivos.

    Parámetros de consulta:
    - `q` (str): Palabra clave para buscar en el nombre del producto o las etiquetas.
    - `animal_type` (str): Tipo de animal relacionado con el producto.
    - `tags` (list[str]): Lista de etiquetas para filtrar los productos.

    Returns:
        Response: Respuesta JSON con una lista de productos filtrados o un mensaje de error.
    """
    try:
        # Obtener los parámetros de consulta
        query = request.args.get('q', '').lower()  # Palabra clave de búsqueda
        animal_type = request.args.get('animal_type', '').lower()  # Tipo de animal
        tags = request.args.getlist('tags')  # Lista de etiquetas para el filtro

        # Construir la consulta base para la base de datos
        base_query = """
        SELECT id, name, description, price, category, animal_type, brand, stock, images, specifications, tags, 
               average_rating, created_at, updated_at
        FROM products
        WHERE 
        """
        # Parámetros de la consulta
        params = {}

        # Añadir filtros dinámicamente a la consulta
        filters = []
        if query:
            if len(query) == 36:  # Verificar si el `query` tiene formato de UUID
                filters.append("id::text = :query_id")  # Filtrar por ID
                params['query_id'] = query
            else:
                filters.append("LOWER(name) LIKE :query OR LOWER(tags::text) LIKE :query")  # Buscar en nombre o etiquetas
                params['query'] = f"%{query}%"
        if animal_type:
            filters.append("LOWER(animal_type) = :animal_type")  # Filtrar por tipo de animal
            params['animal_type'] = animal_type
        if tags:
            filters.append("array_to_string(tags, ',') ILIKE :tags")  # Filtrar por etiquetas
            params['tags'] = f"%{','.join(tags)}%"

        # Completar la consulta añadiendo los filtros dinámicos
        base_query += " AND ".join(filters)

        # Ejecutar la consulta SQL con los parámetros proporcionados
        result = db.session.execute(base_query, params).fetchall()

        # Procesar los resultados y convertirlos en formato JSON
        products = [{
            'id': str(row['id']),
            'name': row['name'],
            'description': row['description'],
            'price': row['price'],
            'category': str(row['category']),
            'animal_type': row['animal_type'],
            'brand': row['brand'],
            'stock': row['stock'],
            'images': row['images'],
            'specifications': row['specifications'],
            'tags': row['tags'],
            'average_rating': row['average_rating'],
            'created_at': row['created_at'].isoformat(),  # Convertir fechas a ISO 8601
            'updated_at': row['updated_at'].isoformat()   # Convertir fechas a ISO 8601
        } for row in result]

        # Devolver la lista de productos en formato JSON
        return jsonify({'products': products}), 200
    except Exception as e:
        # Manejar errores y devolver un mensaje descriptivo
        print(f"Error al listar productos: {e}")
        return jsonify({'message': f'Error al listar productos: {str(e)}'}), 500


# Cache y mecanismos de sincronización
reviews_summary_cache = {}  # Caché para almacenar resúmenes de reseñas por producto
review_events = {}  # Eventos para sincronización de respuestas de reseñas
cache_lock = Lock()  # Lock para proteger el acceso a los datos compartidos

def consume_reviews_responses():
    """
    Consumidor de Kafka para el tópico 'reviews-responses'.

    Este consumidor escucha mensajes en el tópico `reviews-responses`, que contienen resúmenes de reseñas 
    para productos específicos. Los datos se almacenan en una caché global protegida por un lock. Además, 
    se utiliza un mecanismo de eventos para notificar a los procesos que esperan por estos datos.

    Flujo:
    1. Inicializa un consumidor de Kafka para el tópico `reviews-responses`.
    2. Procesa cada mensaje recibido y extrae el `product_id` y los datos de reseñas.
    3. Almacena los datos en un caché compartido (`reviews_summary_cache`) utilizando un lock.
    4. Notifica a los procesos que esperan respuestas para un `product_id` utilizando eventos.

    Args:
        None

    Returns:
        None
    """
    try:
        print("Intentando inicializar el consumidor reviews de Kafka...")
        consumer = KafkaConsumer(
            'reviews-responses',  # Tópico para respuestas de reseñas
            bootstrap_servers=KAFKA_BROKER,  # Dirección del broker de Kafka
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),  # Deserializar mensajes como JSON
            group_id=f"product-service-{random.randint(1, 100000)}",  # Grupo único para consumidores
            auto_offset_reset='latest'  # Comenzar desde los mensajes más recientes
        )
        print("Iniciando consumo del tópico 'reviews-responses'")

        for message in consumer:
            data = message.value  # Extraer datos del mensaje
            print("data,", data)  # Log de depuración
            product_id = data.get('product_id')  # Identificador del producto

            # Crear un resumen de reseñas basado en los datos recibidos
            reviews_summary = {
                'total_reviews': data.get('total_reviews', 0),
                'average_rating': data.get('average_rating', 0.0),
                'helpful_votes': data.get('helpful_votes', 0)
            }

            if product_id:
                with cache_lock:  # Usar lock para proteger la caché compartida
                    reviews_summary_cache[product_id] = reviews_summary
                    print(f"Reseñas almacenadas en cache para producto {product_id}")

                    # Notificar al evento asociado al `product_id`
                    if product_id in review_events:
                        review_events[product_id].set()  # Activar el evento
                        del review_events[product_id]  # Eliminar el evento después de la notificación

    except Exception as e:
        print(f"Error en el consumidor de Kafka para 'reviews-responses': {e}")

# Iniciar el consumidor en un hilo separado para ejecución en segundo plano
threading.Thread(target=consume_reviews_responses, daemon=True).start()

# Endpoint para obtener detalles de un producto
@app.route('/api/products/<uuid:product_id>', methods=['GET'])
@token_required
def get_product(product_id):
    """
    Endpoint para obtener los detalles de un producto específico.

    Este endpoint devuelve información detallada de un producto, como nombre, descripción, precio,
    categoría, stock, e imágenes. Además, solicita las reseñas del producto mediante Kafka y las 
    incluye en la respuesta si están disponibles.

    Flujo:
    1. Consulta la base de datos para obtener detalles del producto.
    2. Si el producto existe:
        - Publica una solicitud de reseñas en Kafka.
        - Espera la respuesta de reseñas usando un evento de sincronización.
        - Si las reseñas están disponibles, las incluye en la respuesta.
    3. Si el producto no se encuentra, devuelve un error 404.
    4. Maneja errores generales con una respuesta 500.

    Args:
        product_id (uuid): ID del producto a consultar.

    Returns:
        Response: JSON con los detalles del producto y, si están disponibles, un resumen de reseñas.
    """
    try:
        # Consulta SQL para obtener los detalles del producto
        query = """
        SELECT id, name, description, price, category, stock, images, created_at, updated_at
        FROM products
        WHERE id = :product_id
        """
        result = db.session.execute(query, {'product_id': str(product_id)}).fetchone()

        # Extraer el token JWT del encabezado de la solicitud
        token = request.headers.get('Authorization').split(" ")[1] 

        # Verificar si el producto existe
        if not result:
            return jsonify({"message": "Producto no encontrado"}), 404

        # Construir el diccionario con los detalles del producto
        product_details = {
            'id': str(result['id']),
            'name': result['name'],
            'description': result['description'],
            'price': result['price'],
            'category': str(result['category']),
            'stock': result['stock'],
            'images': result['images'],
            'created_at': result['created_at'].isoformat() if result['created_at'] else None,
            'updated_at': result['updated_at'].isoformat() if result['updated_at'] else None,
        }

        # Crear un evento de sincronización para las reseñas
        event = Event()
        with cache_lock:
            review_events[str(product_id)] = event
        
        # Preparar datos para la solicitud de reseñas y publicarlos en Kafka
        request_data = {
            'product_id': str(product_id),
            "token": token  
        }

        try:
            producer.send('reviews-requests', request_data)  # Publicar en Kafka
            producer.flush()
            print(f"Solicitud de reseñas enviada a Kafka para producto {product_id}")
        except Exception as kafka_error:
            print(f"Error al enviar solicitud a Kafka: {str(kafka_error)}")
            return jsonify({
                "product": product_details,
                "reviews_summary": [],
                "message": "Error al solicitar las reseñas."
            }), 500

        # Esperar la respuesta del consumidor de Kafka
        timeout = 10  # Tiempo límite en segundos
        if not event.wait(timeout):
            print(f"Timeout esperando resumen de reseñas para producto {product_id}")
            reviews_summary = []
        else:
            # Obtener el resumen de reseñas desde el caché
            with cache_lock:
                reviews_summary = reviews_summary_cache.pop(str(product_id), [])
                print("Reseñas recibidas:", reviews_summary)

        # Construir la respuesta final con los detalles del producto y las reseñas
        return jsonify({
            'product': product_details,
            'reviews_summary': reviews_summary
        }), 200

    except Exception as e:
        # Manejar errores generales
        print(f"Error al obtener detalles del producto: {str(e)}")
        return jsonify({"message": f"Error interno: {str(e)}"}), 500



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000,debug=True)
