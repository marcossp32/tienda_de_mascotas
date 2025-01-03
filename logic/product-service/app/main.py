from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from kafka import KafkaConsumer, KafkaProducer
import json
import os
import threading
from threading import Lock, Event
from datetime import datetime
import random
import sys
from uuid import UUID
from functools import wraps
import jwt

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)


# Configuración de Flask
app = Flask(__name__)

database_url = os.getenv("DATABASE_URL", "postgresql://postgres:12345@postgres-service.default.svc.cluster.local:5432/petstore")
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Configuración de Kafka
KAFKA_BROKER = os.getenv("KAFKA_BROKER", "localhost:9092")

producer = KafkaProducer(
    bootstrap_servers=KAFKA_BROKER,
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

SECRET_KEY = os.getenv("SECRET_KEY", "supersecretkey")

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None

        # Verificar si el token está presente en el encabezado Authorization
        if 'Authorization' in request.headers:
            try:
                auth_header = request.headers['Authorization']
                token = auth_header.split(" ")[1]  # Extraer el token después de "Bearer"
            except IndexError:
                return jsonify({'message': 'Formato del token inválido'}), 401

        if not token:
            return jsonify({'message': 'Token faltante'}), 401

        try:
            # Decodificar el token
            data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            request.user_id = data['user_id']  # Pasar user_id al contexto de la solicitud
        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'Token expirado'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'message': 'Token inválido'}), 401

        return f(*args, **kwargs)

    return decorated

def consume_availability_requests():
    try:
        consumer = KafkaConsumer(
            'product-availability-requests',
            bootstrap_servers=KAFKA_BROKER,
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),
            group_id=f'product-service-{random.randint(1, 100000)}',
            auto_offset_reset='latest'
        )
        print("Iniciando consumo del tópico 'product-availability-requests'")

        for message in consumer:
            data = message.value
            product_id = data.get('product_id')
            quantity = data.get('quantity', 1)
            token = data.get("token")

            # Crear encabezados para simular la solicitud
            headers = {
                'Authorization': f'Bearer {token}'
            }
            
            # Usar app.test_request_context con encabezados simulados
            with app.test_request_context(f"/api/products?q={product_id}", headers=headers):
                try:
                    response = list_products()

                    # Verificar si `response` es una tupla
                    if isinstance(response, tuple):
                        response_data, status_code = response
                    else:
                        response_data = response
                        status_code = 200

                    # Verificar el estado HTTP de la respuesta
                    if status_code == 200:
                        products = response_data.get_json().get('products', [])
                        print(f"Productos devueltos: {products}")  # Depuración
                        product = next((p for p in products if str(p['id']) == str(product_id)), None)

                        if product:
                            print(f"Producto encontrado: {product}")  # Depuración
                            stock = product.get('stock', 0)
                            price = product.get('price', 0)
                            available = stock >= quantity
                        else:
                            print(f"Producto no encontrado con ID: {product_id}")  # Depuración
                            stock = 0
                            price = 0
                            available = False

                        # Respuesta para Kafka
                        kafka_response = {
                            "product_id": product_id,
                            "available": available,
                            "stock": stock,
                            "price": price
                        }
                        producer.send('product-availability-responses', kafka_response)
                        producer.flush()
                        print(f"Respuesta de disponibilidad enviada: {kafka_response}")
                    else:
                        print(f"Error al consultar productos: {status_code}")
                except Exception as e:
                    print(f"Error al procesar disponibilidad para producto {product_id}: {str(e)}")
    except Exception as e:
        print(f"Error en el consumidor de Kafka para 'product-availability-requests': {e}")



def consume_search_requests():
    try:
        print("Intentando inicializar el consumidor de Kafka...")
        consumer = KafkaConsumer(
            'search-requests',
            bootstrap_servers=KAFKA_BROKER,
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),
            group_id=f"product-service-{random.randint(1, 100000)}",
            auto_offset_reset='latest'
        )
        print("Iniciando consumo del tópico 'search-requests'")

        for message in consumer:
            data = message.value
            query = data.get('query', '')
            token = data.get("token")

            # Crear encabezados para simular la solicitud
            headers = {
                'Authorization': f'Bearer {token}'
            }
            
            # Usar app.test_request_context con encabezados simulados
            with app.test_request_context(f"/api/products?q={query}", headers=headers):
            
                # Llamar directamente al endpoint
                response = list_products()
                status_code = response[1]

                if status_code == 200:
                    products = response[0].get_json()['products']
                    # Publicar resultados en Kafka
                    producer.send('products-responses', {'type': 'product', 'data': products})
                    producer.flush()
                    print(f"Respuesta enviada a Kafka: {products}")
                else:
                    print(f"Error al consultar productos: {status_code}")

    except Exception as e:
        print(f"Error en el consumidor de Kafka para 'search-requests': {e}")


# Consumidor de Kafka para actualizaciones de inventario
def consume_inventory_updates():
    consumer = KafkaConsumer(
        'inventory-updates',
        bootstrap_servers=KAFKA_BROKER,
        value_deserializer=lambda x: json.loads(x.decode('utf-8')),
        group_id=f'product-service-{random.randint(1, 100000)}',
        auto_offset_reset='latest'
    )
    print("Iniciando consumo del tópico 'inventory-updates'")

    for message in consumer:
        data = message.value
        product_id = data.get('product_id')
        quantity_change = data.get('quantity', 0)
        print(f"Actualización de inventario recibida para producto {product_id}, cambio en cantidad: {quantity_change}")

        with app.app_context():
            try:
                query = "SELECT stock FROM products WHERE id = :product_id"
                result = db.session.execute(query, {'product_id': product_id}).fetchone()

                if result:
                    current_stock = result['stock']
                    new_stock = current_stock + quantity_change
                    if new_stock < 0:
                        print(f"Error: El inventario no puede ser negativo para producto {product_id}")
                        continue

                    update_query = "UPDATE products SET stock = :new_stock, updated_at = :updated_at WHERE id = :product_id"
                    db.session.execute(update_query, {
                        'new_stock': new_stock,
                        'updated_at': datetime.utcnow(),
                        'product_id': product_id
                    })
                    db.session.commit()
                    print(f"Inventario actualizado para producto {product_id}: {new_stock}")
                else:
                    print(f"Producto {product_id} no encontrado.")
            except Exception as e:
                print(f"Error al actualizar inventario para producto {product_id}: {str(e)}")

# Iniciar consumidores en hilos separados
threading.Thread(target=consume_search_requests, daemon=True).start()
threading.Thread(target=consume_availability_requests, daemon=True).start()
threading.Thread(target=consume_inventory_updates, daemon=True).start()


@app.route('/api/products', methods=['GET'])
@token_required
def list_products():
    try:
        # Obtener los parámetros de consulta
        query = request.args.get('q', '').lower()
        animal_type = request.args.get('animal_type', '').lower()
        tags = request.args.getlist('tags')  # Lista de tags si se pasan varios

        # Construir consulta base
        base_query = """
        SELECT id, name, description, price, category, animal_type, brand, stock, images, specifications, tags, average_rating, created_at, updated_at
        FROM products
        WHERE 
        """
        # Parámetros de la consulta
        params = {}

        # Añadir filtros dinámicamente
        filters = []
        if query:
            if len(query) == 36:  # Si query tiene formato UUID
                filters.append("id::text = :query_id")
                params['query_id'] = query
            else:
                filters.append("LOWER(name) LIKE :query OR LOWER(tags::text) LIKE :query")
                params['query'] = f"%{query}%"
        if animal_type:
            filters.append("LOWER(animal_type) = :animal_type")
            params['animal_type'] = animal_type
        if tags:
            filters.append("array_to_string(tags, ',') ILIKE :tags")
            params['tags'] = f"%{','.join(tags)}%"

        # Completar la consulta con los filtros
        base_query += " AND ".join(filters)

        # Ejecutar consulta
        result = db.session.execute(base_query, params).fetchall()

        # Procesar resultados
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
            'created_at': row['created_at'].isoformat(),
            'updated_at': row['updated_at'].isoformat()
        } for row in result]

        return jsonify({'products': products}), 200
    except Exception as e:
        print(f"Error al listar productos: {e}")
        return jsonify({'message': f'Error al listar productos: {str(e)}'}), 500


# Cache y mecanismos de sincronización
reviews_summary_cache = {}
review_events = {}
cache_lock = Lock()

# Consumidor de respuestas de reseñas
def consume_reviews_responses():
    try:
        print("Intentando inicializar el consumidor reviews de Kafka...")
        consumer = KafkaConsumer(
            'reviews-responses',
            bootstrap_servers=KAFKA_BROKER,
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),
            group_id=f"product-service-{random.randint(1, 100000)}",
            auto_offset_reset='latest'
        )
        print("Iniciando consumo del tópico 'reviews-responses'")

        for message in consumer:
            data = message.value
            print("data," ,data)
            product_id = data.get('product_id')

            reviews_summary = {
                'total_reviews': data.get('total_reviews', 0),
                'average_rating': data.get('average_rating', 0.0),
                'helpful_votes': data.get('helpful_votes', 0)
            }

            if product_id:
                with cache_lock:
                    reviews_summary_cache[product_id] = reviews_summary
                    print(f"Reseñas almacenadas en cache para producto {product_id}")

                    print("aaa:", reviews_summary)
                    # Notificar al evento de sincronización
                    if product_id in review_events:
                        print("Entra noti")
                        review_events[product_id].set()
                        del review_events[product_id]

    except Exception as e:
        print(f"Error en el consumidor de Kafka para 'reviews-responses': {e}")

# Iniciar consumidor en un hilo separado
threading.Thread(target=consume_reviews_responses, daemon=True).start()

# Endpoint para obtener detalles de un producto
@app.route('/api/products/<uuid:product_id>', methods=['GET'])
@token_required
def get_product(product_id):
    try:
        # Consulta a la base de datos para obtener detalles del producto
        query = """
        SELECT id, name, description, price, category, stock, images, created_at, updated_at
        FROM products
        WHERE id = :product_id
        """
        result = db.session.execute(query, {'product_id': str(product_id)}).fetchone()

        token = request.headers.get('Authorization').split(" ")[1] 

        if not result:
            return jsonify({"message": "Producto no encontrado"}), 404

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

        # Crear un evento para sincronización
        event = Event()
        with cache_lock:
            review_events[str(product_id)] = event
        
        # Publicar solicitud en Kafka con el token
        request_data = {
            'product_id': str(product_id),
            "token": token  
        }

        # Publicar solicitud de reseñas en Kafka
        try:
            producer.send('reviews-requests', request_data)
            producer.flush()
            print(f"Solicitud de reseñas enviada a Kafka para producto {product_id}")
        except Exception as kafka_error:
            print(f"Error al enviar solicitud a Kafka: {str(kafka_error)}")
            return jsonify({
                "product": product_details,
                "reviews_summary": [],
                "message": "Error al solicitar las reseñas."
            }), 500

        # Esperar respuesta del consumidor de Kafka
        timeout = 10  # Tiempo límite en segundos
        if not event.wait(timeout):
            print(f"Timeout esperando resumen de reseñas para producto {product_id}")
            reviews_summary = []
        else:
            # Obtener resumen desde el cache
            with cache_lock:
                reviews_summary = reviews_summary_cache.pop(str(product_id), [])
                print("Reseñas 1:",reviews_summary)

        print("Reseñas 2:",reviews_summary)
        return jsonify({
            'product': product_details,
            'reviews_summary': reviews_summary
        }), 200

    except Exception as e:
        print(f"Error al obtener detalles del producto: {str(e)}")
        return jsonify({"message": f"Error interno: {str(e)}"}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
