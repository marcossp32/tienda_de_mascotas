from flask import Flask, jsonify, request
from kafka import KafkaProducer, KafkaConsumer
from functools import wraps

import json
import os
import random
import sys
import jwt

# Configurar la salida estándar para manejar el buffering correctamente
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# Configuración de Flask
app = Flask(__name__)

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

def consume_last_message(topic):
    """
    Consume el último mensaje disponible en el tópico especificado de Kafka.

    Este consumidor:
    - Se conecta al tópico de Kafka especificado.
    - Navega hasta el último offset de cada partición.
    - Recupera el último mensaje disponible en el log.
    - No realiza confirmaciones automáticas de mensajes para evitar conflictos en otros consumidores.

    Args:
        topic (str): Nombre del tópico de Kafka a consumir.

    Returns:
        dict or None: El contenido del último mensaje en formato JSON, o `None` si no hay mensajes disponibles.
    """
    consumer = KafkaConsumer(
        topic,
        bootstrap_servers=KAFKA_BROKER,
        value_deserializer=lambda x: json.loads(x.decode('utf-8')),
        group_id=None,  # Usar un grupo único para evitar conflictos de offsets
        enable_auto_commit=False  # No confirmar mensajes automáticamente
    )

    try:
        # Suscribirse al tópico
        consumer.subscribe([topic])
        consumer.poll(timeout_ms=1000)  # Forzar la suscripción

        # Obtener particiones asignadas y calcular el último offset disponible
        last_offset = {}
        for partition in consumer.assignment():
            consumer.seek_to_end(partition)  # Ir al final de cada partición
            last_offset[partition] = consumer.position(partition) - 1  # Calcular último offset

        # Leer el último mensaje de cada partición
        for partition, offset in last_offset.items():
            if offset >= 0:  # Si hay mensajes en la partición
                consumer.seek(partition, offset)  # Posicionarse en el último offset
                messages = consumer.poll(timeout_ms=1000)  # Obtener los mensajes
                for _, records in messages.items():
                    for record in records:
                        print(f"Último mensaje recibido: {record.value}")  # Log con `print`
                        return record.value  # Retornar directamente el valor del mensaje

        print("No se encontró ningún mensaje en el log actual.")  # Log con `print`
        return None

    finally:
        consumer.close()  # Cerrar el consumidor para liberar recursos


@app.route('/api/search', methods=['GET'])
@token_required
def search():
    """
    Endpoint de búsqueda.

    Este endpoint permite a los usuarios realizar búsquedas de productos y categorías en el sistema.
    Envía las solicitudes de búsqueda a Kafka y consume los resultados de los tópicos relacionados.

    Returns:
        Response: Respuesta JSON con los resultados de búsqueda de productos y categorías, o un mensaje de error.
    """
    try:
        # Obtener el término de búsqueda desde los parámetros de consulta
        query = request.args.get('q', '').strip().lower()
        # Extraer el token del encabezado Authorization
        token = request.headers.get('Authorization').split(" ")[1]

        # Crear la solicitud para Kafka
        request_data = {
            "query": query,
            "token": token  
        }
        try:
            # Enviar la solicitud al tópico 'search-requests'
            producer.send('search-requests', request_data)
            producer.flush()
            print(f"Solicitud enviada a Kafka: {request_data}")  # Reemplazo de logging.info
        except Exception as e:
            print(f"Error al enviar solicitud a Kafka: {e}")  # Reemplazo de logging.error
            return jsonify({"message": "Error al enviar la solicitud a Kafka."}), 500

        # Consumir los últimos mensajes de los tópicos de respuestas
        print("Intentando consumir los últimos mensajes.")  # Reemplazo de logging.info
        product_message = consume_last_message('products-responses')
        category_message = consume_last_message('categories-responses')

        # Procesar resultados de productos
        if product_message:
            print(f"Mensaje de productos procesado: {product_message}")  # Reemplazo de logging.info
            product_results = product_message.get("data", [])
        else:
            print("No se encontraron mensajes en el tópico de productos.")  # Reemplazo de logging.warning
            product_results = []

        # Procesar resultados de categorías
        if category_message:
            print(f"Mensaje de categorías procesado: {category_message}")  # Reemplazo de logging.info
            category_results = category_message.get("data", [])
        else:
            print("No se encontraron mensajes en el tópico de categorías.")  # Reemplazo de logging.warning
            category_results = []

        # Formatear la respuesta final
        response_data = {
            "products": [{"type": "product", "data": product_results}],
            "categories": [{"type": "category", "data": category_results}]
        }

        return jsonify(response_data), 200
    except Exception as e:
        print(f"Error interno en el endpoint /api/search: {e}")  # Reemplazo de logging.error
        return jsonify({"message": "Error interno en el servidor.", "error": str(e)}), 500



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
