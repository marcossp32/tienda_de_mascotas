from flask import Flask, jsonify, request
from kafka import KafkaProducer, KafkaConsumer
import json
import os
import random
import sys
import logging
from functools import wraps
import jwt

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,  # Mostrar logs informativos
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

# Configuración de Flask
app = Flask(__name__)

# Configuración de Kafka
KAFKA_BROKER = os.getenv("KAFKA_BROKER", "localhost:9092")
try:
    producer = KafkaProducer(
        bootstrap_servers=KAFKA_BROKER,
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )
    logging.info("Productor de Kafka inicializado correctamente")
except Exception as e:
    logging.error(f"Error al inicializar el productor de Kafka: {e}")
    sys.exit(1)

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

def consume_last_message(topic):
    """Consume el último mensaje disponible en el tópico."""
    consumer = KafkaConsumer(
        topic,
        bootstrap_servers=KAFKA_BROKER,
        value_deserializer=lambda x: json.loads(x.decode('utf-8')),
        group_id=None,  # Usar un grupo único para evitar conflictos de offsets
        enable_auto_commit=False  # No queremos confirmar mensajes
    )

    try:
        # Suscribirse al tópico
        consumer.subscribe([topic])
        consumer.poll(timeout_ms=1000)  # Forzar la suscripción

        # Obtener particiones asignadas y el último offset disponible
        last_offset = {}
        for partition in consumer.assignment():
            consumer.seek_to_end(partition)
            last_offset[partition] = consumer.position(partition) - 1

        # Posicionar al último offset y leer el mensaje
        for partition, offset in last_offset.items():
            if offset >= 0:
                consumer.seek(partition, offset)
                messages = consumer.poll(timeout_ms=1000)
                for _, records in messages.items():
                    for record in records:
                        logging.info(f"Último mensaje recibido: {record.value}")
                        return record.value  # Retorna directamente el valor del mensaje
        logging.warning("No se encontró ningún mensaje en el log actual.")
        return None
    finally:
        consumer.close()

@app.route('/api/search', methods=['GET'])
@token_required
def search():
    """Endpoint de búsqueda."""
    try:
        query = request.args.get('q', '').strip().lower()
        token = request.headers.get('Authorization').split(" ")[1]  # Extraer el token

        # Publicar solicitud en Kafka con el token
        request_data = {
            "query": query,
            "token": token  
        }
        try:
            producer.send('search-requests', request_data)
            producer.flush()
            logging.info(f"Solicitud enviada a Kafka: {request_data}")
        except Exception as e:
            logging.error(f"Error al enviar solicitud a Kafka: {e}")
            return jsonify({"message": "Error al enviar la solicitud a Kafka."}), 500

        # Consumir el último mensaje de ambos tópicos
        logging.info("Intentando consumir los últimos mensajes.")
        product_message = consume_last_message('products-responses')
        category_message = consume_last_message('categories-responses')

        # Procesar resultados de productos
        if product_message:
            logging.info(f"Mensaje de productos procesado: {product_message}")
            product_results = product_message.get("data", [])
        else:
            logging.warning("No se encontraron mensajes en el tópico de productos.")
            product_results = []

        # Procesar resultados de categorías
        if category_message:
            logging.info(f"Mensaje de categorías procesado: {category_message}")
            category_results = category_message.get("data", [])
        else:
            logging.warning("No se encontraron mensajes en el tópico de categorías.")
            category_results = []

        # Formatear la respuesta final
        response_data = {
            "products": [{"type": "product", "data": product_results}],
            "categories": [{"type": "category", "data": category_results}]
        }

        return jsonify(response_data), 200
    except Exception as e:
        logging.error(f"Error interno en el endpoint /api/search: {e}")
        return jsonify({"message": "Error interno en el servidor.", "error": str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
