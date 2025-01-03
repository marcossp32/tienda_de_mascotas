from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from kafka import KafkaConsumer, KafkaProducer
import threading
import json
import os
import sys
import requests
from functools import wraps
import jwt

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)


app = Flask(__name__)

# Configuración de Flask y SQLAlchemy
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:12345@localhost:5432/petstore")
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
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

def consume_reviews_requests():
    try:
        consumer = KafkaConsumer(
            'reviews-requests',
            bootstrap_servers=KAFKA_BROKER,
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),
            group_id='review-service',
            auto_offset_reset='earliest'
        )
        print("Iniciando consumo del tópico 'reviews-requests'")

        for message in consumer:
            data = message.value
            product_id = data.get('product_id')
            token = data.get("token")

            if not token:
                print(f"Token faltante en el mensaje del producto {product_id}")
                continue 

            # Crear encabezados para simular la solicitud
            headers = {
                'Authorization': f'Bearer {token}'
            }

            # Realizar una llamada al endpoint para obtener las reseñas
            try:
                response = requests.get(
                    f"http://localhost:5000/api/products/{product_id}/reviews",
                    headers=headers 
                )
                
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

                    # Publicar resumen en Kafka
                    producer.send('reviews-responses', summary)
                    producer.flush()
                    print(f"Resumen de reseñas enviado para producto {product_id}")
                else:
                    print(f"Error al obtener reseñas desde el endpoint: {response.status_code}")

            except requests.RequestException as e:
                print(f"Error en la solicitud HTTP para producto {product_id}: {str(e)}")

    except Exception as e:
        print(f"Error en el consumidor de Kafka para 'reviews-requests': {str(e)}")

# Iniciar el consumidor en un hilo separado
threading.Thread(target=consume_reviews_requests, daemon=True).start()



# Endpoint para listar reseñas de un producto
@app.route('/api/products/<uuid:product_id>/reviews', methods=['GET'])
@token_required
def list_reviews(product_id):
    try:
        # Consultar reseñas desde la base de datos
        query = """
        SELECT id, product_id, user_id, rating, title, comment, helpful, created_at, updated_at
        FROM reviews
        WHERE product_id = :product_id
        """
        result = db.session.execute(query, {'product_id': str(product_id)}).fetchall()

        # Construir la respuesta
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

        return jsonify({'reviews': reviews}), 200

    except Exception as e:
        print(f"Error al obtener reseñas: {str(e)}")
        return jsonify({"message": f"Error interno: {str(e)}"}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000,debug=True)
