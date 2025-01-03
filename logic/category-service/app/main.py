from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from kafka import KafkaConsumer, KafkaProducer
import json
import os
import threading
import sys
import random
from flask import Response
from functools import wraps
import jwt

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# Configuración de Flask y Kafka
app = Flask(__name__)

# Configuración de la base de datos
database_url = os.getenv(
    "DATABASE_URL", 
    "postgresql://postgres:12345@postgres-service.default.svc.cluster.local:5432/petstore"
)
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

# Consumidor de Kafka para solicitudes de búsqueda
def consume_search_requests():
    try:
        print("Intentando inicializar el consumidor de Kafka...")
        consumer = KafkaConsumer(
            'search-requests',
            bootstrap_servers=KAFKA_BROKER,
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),
            group_id=f"category-service-{random.randint(1, 100000)}",
            auto_offset_reset='latest'
        )
        print("Iniciando consumo del tópico 'search-requests'")

        for message in consumer:
            data = message.value
            query = data.get("query", "")
            token = data.get("token")

            # Crear encabezados para simular la solicitud
            headers = {
                'Authorization': f'Bearer {token}'
            }
            
            # Usar app.test_request_context con encabezados simulados
            with app.test_request_context(f"/api/categories?q={query}", headers=headers):
                response: Response = app.full_dispatch_request()

                if response.status_code == 200:
                    categories = response.get_json()['categories']
                    # Publicar resultados en Kafka
                    producer.send('categories-responses', {'type': 'category', 'data': categories})
                    producer.flush()
                    print(f"Respuesta enviada a Kafka: {categories}")
                else:
                    print(f"Error al consultar categorías: {response.status_code}")

    except Exception as e:
        print(f"Error en el consumidor de Kafka para 'search-requests': {e}")


# Iniciar el consumidor en un hilo separado
threading.Thread(target=consume_search_requests, daemon=True).start()

# Endpoint para listar categorías
@app.route('/api/categories', methods=['GET'])
@token_required
def list_categories():
    try:
        # Obtener los parámetros de consulta
        query = request.args.get('q', '').lower()
        parent_category = request.args.get('parent')
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 10))
        offset = (page - 1) * limit

        # Construir consulta base
        base_query = """
        SELECT id, name, description, parent_category, image_url, active
        FROM categories
        WHERE active = TRUE AND LOWER(name) LIKE :query
        """
        params = {'query': f"%{query}%"}
        if parent_category:
            base_query += " AND parent_category = :parent_category"
            params['parent_category'] = parent_category

        base_query += " LIMIT :limit OFFSET :offset"
        params.update({'limit': limit, 'offset': offset})

        # Ejecutar consulta
        result = db.session.execute(base_query, params).fetchall()

        # Procesar resultados
        categories = [{
            'id': str(row['id']),
            'name': row['name'],
            'description': row['description'],
            'parent_category': str(row['parent_category']) if row['parent_category'] else None,
            'image_url': row['image_url']
        } for row in result]

        return jsonify({'categories': categories}), 200
    except Exception as e:
        return jsonify({'message': f'Error al listar categorías: {str(e)}'}), 500



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000,debug=True)
