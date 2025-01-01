from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from kafka import KafkaProducer, KafkaConsumer
import json
import os
import uuid
from datetime import datetime
import random
import sys
from threading import Thread, Event, Lock

from queue import Queue, Empty
import time

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

app = Flask(__name__)

# Configuración de Flask y SQLAlchemy
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


# 4.1 Obtener carrito actual y publicar en Kafka
@app.route('/api/cart', methods=['GET'])
def get_cart():
    try:
        # Simulamos un usuario autenticado
        user_id = request.args.get('user_id')  # En producción, se obtendría del token JWT

        if not user_id:
            return jsonify({"message": "El campo 'user_id' es obligatorio."}), 400

        # Consultar el carrito del usuario
        cart_query = """
        SELECT id, total_amount, created_at, updated_at
        FROM carts
        WHERE user_id = :user_id
        """
        cart = db.session.execute(cart_query, {"user_id": user_id}).fetchone()

        if not cart:
            response = {"message": "Carrito no encontrado."}
            producer.send('cart-responses', {"user_id": user_id, "response": response})
            producer.flush()
            return jsonify(response), 404

        cart_id = cart["id"]

        # Consultar los ítems del carrito
        items_query = """
        SELECT ci.id AS cart_item_id, ci.quantity, ci.price, 
               p.id AS product_id, p.name AS product_name, p.images AS product_images
        FROM cart_items ci
        JOIN products p ON ci.product_id = p.id
        WHERE ci.cart_id = :cart_id
        """
        items = db.session.execute(items_query, {"cart_id": cart_id}).fetchall()

        # Construir la respuesta
        cart_items = [{
            "cart_item_id": str(item["cart_item_id"]),
            "product_id": str(item["product_id"]),
            "product_name": item["product_name"],
            "product_images": item["product_images"],
            "quantity": item["quantity"],
            "price": item["price"]
        } for item in items]

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
        print(f"Respuesta del carrito publicada en Kafka: {kafka_message}")

        return jsonify(response), 200

    except Exception as e:
        error_message = f"Error al obtener el carrito: {str(e)}"
        print(error_message)
        producer.send('cart-responses', {"user_id": user_id, "response": {"message": error_message}})
        producer.flush()
        return jsonify({"message": error_message}), 500



# Diccionarios y locks
availability_queues = {}
availability_lock = Lock()

def consume_availability_responses():
    consumer = KafkaConsumer(
        'product-availability-responses',
        bootstrap_servers=KAFKA_BROKER,
        value_deserializer=lambda x: json.loads(x.decode('utf-8')),
        group_id='cart-service',
        enable_auto_commit=True,
        auto_offset_reset='latest'
    )
    print("[Cart-Service] Esperando respuestas de disponibilidad en Kafka...")

    for message in consumer:
        response = message.value
        product_id = response.get('product_id')
        timestamp = time.time()

        print(f"[Cart-Service] {datetime.now()} Mensaje recibido de Kafka: {response}, Timestamp: {timestamp}")

        with availability_lock:
            # Colocar el mensaje en la cola si existe
            if product_id in availability_queues:
                try:
                    availability_queues[product_id].put_nowait(response)
                    print(f"[Cart-Service] Respuesta encolada para product_id={product_id}")
                except Full:
                    print(f"[Cart-Service] La cola para product_id={product_id} está llena. Respuesta descartada.")

@app.route('/api/cart/items', methods=['POST'])
def add_to_cart():
    try:
        data = request.get_json()
        product_id = data.get('product_id')
        quantity = data.get('quantity', 1)
        user_id = data.get('user_id')

        if not product_id or not user_id:
            return jsonify({"message": "Los campos 'product_id' y 'user_id' son obligatorios."}), 400

        print(f"[Cart-Service] Solicitud recibida: user_id={user_id}, product_id={product_id}, cantidad={quantity}")

        # Crear una cola para manejar la respuesta si no existe
        with availability_lock:
            if product_id not in availability_queues:
                availability_queues[product_id] = Queue(maxsize=1)

        # Publicar solicitud de disponibilidad
        availability_request = {"product_id": product_id, "quantity": quantity}
        producer.send('product-availability-requests', availability_request)
        producer.flush()
        print(f"[Cart-Service] {datetime.now()} Solicitud de disponibilidad enviada: {availability_request}")

        # Esperar respuesta con timeout
        try:
            response = availability_queues[product_id].get(timeout=15)
            print(f"[Cart-Service] {datetime.now()} Respuesta procesada para product_id={product_id}: {response}")
        except Empty:
            
            timestamp = time.time()

            print(f"[Cart-Service] Timeout esperando disponibilidad para product_id={product_id}, time:{timestamp}")
            return jsonify({"message": "No se pudo verificar la disponibilidad del producto a tiempo."}), 500

        # Procesar la respuesta
        if not response.get('available', False):
            print(f"[Cart-Service] Producto no disponible: {response}")
            return jsonify({"message": "El producto no está disponible."}), 400

        # Lógica para añadir al carrito
        print(f"[Cart-Service] Producto disponible, añadiendo al carrito: {response}")
        with db.session.begin():
            cart = db.session.execute(
                "SELECT id, total_amount FROM carts WHERE user_id = :user_id",
                {"user_id": user_id}
            ).fetchone()

            if not cart:
                cart_id = str(uuid.uuid4())
                db.session.execute(
                    """
                    INSERT INTO carts (id, user_id, total_amount, created_at, updated_at)
                    VALUES (:id, :user_id, 0, :created_at, :updated_at)
                    """,
                    {"id": cart_id, "user_id": user_id, "created_at": datetime.utcnow(), "updated_at": datetime.utcnow()}
                )
                print(f"[Cart-Service] Carrito creado para user_id {user_id}")
                cart_total = 0
            else:
                cart_id = cart['id']
                cart_total = cart['total_amount']
                print(f"[Cart-Service] Carrito existente encontrado: {cart_id} para user_id {user_id}")

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
            print(f"[Cart-Service] Producto {product_id} añadido al carrito {cart_id}")

            new_total = cart_total + (price * quantity)
            db.session.execute(
                """
                UPDATE carts SET total_amount = :total_amount, updated_at = :updated_at
                WHERE id = :cart_id
                """,
                {"total_amount": new_total, "updated_at": datetime.utcnow(), "cart_id": cart_id}
            )
            print(f"[Cart-Service] Total del carrito actualizado a {new_total}")

        # Limpieza de la cola después del procesamiento
        with availability_lock:
            if product_id in availability_queues:
                del availability_queues[product_id]

        return jsonify({"message": "Producto añadido al carrito exitosamente."}), 200

    except Exception as e:
        print(f"[Cart-Service] Error al añadir al carrito: {str(e)}")
        return jsonify({"message": f"Error interno: {str(e)}"}), 500

# Iniciar consumidor de Kafka
Thread(target=consume_availability_responses, daemon=True).start()



# 4.3 Actualizar cantidad de un producto en el carrito
@app.route('/api/cart/items/<int:item_id>', methods=['PUT'])
def update_cart_item(item_id):
    None

# 4.4 Eliminar producto del carrito
@app.route('/api/cart/items/<int:item_id>', methods=['DELETE'])
def delete_cart_item(item_id):
    None

# 4.5 Vaciar carrito
@app.route('/api/cart', methods=['DELETE'])
def clear_cart():
    None

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000,debug=True)
