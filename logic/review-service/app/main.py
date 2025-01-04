from flask_sqlalchemy import SQLAlchemy
from flask import Flask, jsonify, request
from kafka import KafkaConsumer, KafkaProducer
from functools import wraps

import threading
import json
import os
import sys
import requests 
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


def consume_reviews_requests():
    """
    Consumidor para el tópico de Kafka `reviews-requests`.

    Este consumidor escucha solicitudes de reseñas para productos. Cuando recibe una solicitud, 
    realiza una llamada HTTP al endpoint `/api/products/{product_id}/reviews` para obtener las reseñas. 
    Luego, procesa las reseñas para generar un resumen con el número total de reseñas, la calificación 
    promedio y los votos útiles, y lo publica en el tópico `reviews-responses`.

    Flujo:
    1. Conectar al tópico `reviews-requests` en Kafka.
    2. Procesar mensajes entrantes que contienen `product_id` y `token`.
    3. Realizar una solicitud HTTP para obtener las reseñas del producto.
    4. Generar un resumen de las reseñas (total, promedio, votos útiles).
    5. Publicar el resumen en el tópico `reviews-responses`.
    6. Manejar errores, como la falta de tokens o fallos en las solicitudes HTTP.

    Args:
        None

    Returns:
        None
    """
    try:
        # Inicializar el consumidor de Kafka
        consumer = KafkaConsumer(
            'reviews-requests',
            bootstrap_servers=KAFKA_BROKER,
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),
            group_id='review-service',
            auto_offset_reset='earliest'
        )

        # Procesar mensajes del tópico
        for message in consumer:
            data = message.value
            product_id = data.get('product_id')
            token = data.get("token")

            # Verificar si el token está presente
            if not token:
                print(f"Token faltante en el mensaje del producto {product_id}")
                continue 

            # Crear encabezados para la solicitud HTTP
            headers = {
                'Authorization': f'Bearer {token}'
            }

            # Realizar una llamada al endpoint para obtener las reseñas
            try:
                response = requests.get(
                    f"http://localhost:5000/api/products/{product_id}/reviews",
                    headers=headers 
                )
                
                # Si la solicitud HTTP es exitosa
                if response.status_code == 200:
                    reviews = response.json().get('reviews', [])

                    # Crear un resumen de las reseñas
                    total_reviews = len(reviews)
                    average_rating = (
                        sum(review.get('rating', 0) for review in reviews) / total_reviews
                        if total_reviews > 0 else 0
                    )
                    helpful_votes = sum(review.get('helpful', 0) for review in reviews)

                    summary = {
                        'product_id': str(product_id),
                        'total_reviews': total_reviews,
                        'average_rating': round(average_rating, 2),
                        'helpful_votes': helpful_votes
                    }

                    # Publicar el resumen en Kafka
                    producer.send('reviews-responses', summary)
                    producer.flush()
                    print(f"Resumen de reseñas enviado para producto {product_id}")
                else:
                    print(f"Error al obtener reseñas desde el endpoint: {response.status_code}")

            # Manejar errores en la solicitud HTTP
            except requests.RequestException as e:
                print(f"Error en la solicitud HTTP para producto {product_id}: {str(e)}")

    # Manejar errores en el consumidor de Kafka
    except Exception as e:
        print(f"Error en el consumidor de Kafka para 'reviews-requests': {str(e)}")

# Iniciar el consumidor en un hilo separado
threading.Thread(target=consume_reviews_requests, daemon=True).start()



# Endpoint para listar reseñas de un producto
@app.route('/api/products/<uuid:product_id>/reviews', methods=['GET'])
@token_required
def list_reviews(product_id):
    """
    Endpoint para obtener la lista de reseñas de un producto específico.

    Este endpoint permite a un usuario autenticado obtener las reseñas asociadas a un producto
    identificado por `product_id`. Los datos son extraídos de la base de datos, transformados
    en una lista de objetos JSON y devueltos en la respuesta.

    Flujo:
    1. Consultar las reseñas en la base de datos mediante una consulta SQL.
    2. Procesar los resultados para construir una lista de reseñas en formato JSON.
    3. Devolver la lista como respuesta en un objeto JSON.
    4. Manejar posibles errores durante la consulta o procesamiento de datos.

    Args:
        product_id (UUID): Identificador único del producto para el que se solicitan las reseñas.

    Returns:
        Response: Respuesta JSON con la lista de reseñas o un mensaje de error.
    """
    try:
        # Consultar las reseñas desde la base de datos
        query = """
        SELECT id, product_id, user_id, rating, title, comment, helpful, created_at, updated_at
        FROM reviews
        WHERE product_id = :product_id
        """
        result = db.session.execute(query, {'product_id': str(product_id)}).fetchall()

        # Construir la lista de reseñas a partir de los resultados
        reviews = [{
            'id': str(row.id),
            'product_id': str(row.product_id),
            'user_id': str(row.user_id),
            'rating': row.rating,
            'title': row.title,
            'comment': row.comment,
            'helpful': row.helpful,
            'created_at': row.created_at.isoformat() if row.created_at else None,
            'updated_at': row.updated_at.isoformat() if row.updated_at else None
        } for row in result]

        # Devolver las reseñas en formato JSON con un código de estado HTTP 200
        return jsonify({'reviews': reviews}), 200

    except Exception as e:
        # Manejo de errores durante la consulta o el procesamiento de datos
        print(f"Error al obtener reseñas: {str(e)}")
        return jsonify({"message": f"Error interno: {str(e)}"}), 500



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000,debug=True)
