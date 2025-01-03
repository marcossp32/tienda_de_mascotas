from flask import Flask, jsonify, request
from kafka import KafkaProducer, KafkaConsumer
import threading
import json
import uuid
from datetime import datetime
import os
import sys
import random
from flask_sqlalchemy import SQLAlchemy


sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

app = Flask(__name__)

# Configuración de la base de datos y SQLAlchemy desde la variable de entorno DATABASE_URL
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

cart_items_response = []
cart_event = threading.Event()

def consume_cart_items_response():
    consumer = KafkaConsumer(
        "cart-responses",
        bootstrap_servers=KAFKA_BROKER,
        value_deserializer=lambda x: json.loads(x.decode('utf-8')),
        group_id=f"order-service-{random.randint(1, 100000)}",
        auto_offset_reset="latest",
    )
    print("cart consumer iniciado")
    for message in consumer:
        data = message.value
        print("bbbb",data)
        cart_items_response.append(data)
        cart_event.set()
        break


# Inicia el hilo
threading.Thread(target=consume_cart_items_response, daemon=True).start()


address_response = []
address_event = threading.Event()

def consume_address_response():
    consumer = KafkaConsumer(
        "address-responses",
        bootstrap_servers=KAFKA_BROKER,
        value_deserializer=lambda x: json.loads(x.decode('utf-8')),
        group_id=f"order-service-{random.randint(1, 100000)}",
        auto_offset_reset="latest",
    )
    print("address consumer iniciado")
    for message in consumer:
        data = message.value
        print("aaaa",data)
        address_response.append(data)
        address_event.set()
        break

threading.Thread(target=consume_address_response, daemon=True).start()

# 5.1 Crear un nuevo pedido
@app.route('/api/orders', methods=['POST'])
def create_order():
    try:
        data = request.get_json()
        user_id = data.get("user_id")
        payment_method = data.get("payment_method")

        if not user_id or not payment_method:
            return jsonify({"message": "Faltan campos obligatorios (user_id, payment_method)."}), 400

        # 1. Solicitar dirección del usuario
        producer.send("address-requests", {"user_id": user_id})
        producer.flush()
        print(f"Solicitud de dirección enviada a Kafka para user_id {user_id}")

        # 2. Solicitar ítems del carrito
        producer.send("cart-items-requests", {"user_id": user_id})
        producer.flush()
        print(f"Solicitud de ítems del carrito enviada a Kafka para user_id {user_id}")

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

        print("Items del carrito: ", cart_items_response)

        if not isinstance(cart_response, dict) or "response" not in cart_response:
            return jsonify({"message": "Formato inválido del mensaje del carrito."}), 500

        cart_data = cart_response["response"]

        if not isinstance(cart_data, dict) or "items" not in cart_data or not cart_data["items"]:
            return jsonify({"message": "No se encontraron ítems en el carrito."}), 404


        cart_items = cart_data["items"]

        # 3. Crear pedido
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
            print(f"❌ Error al guardar el pedido: {e}")
            return jsonify({"message": "Error al crear el pedido en la base de datos."}), 500

        # Publicar el pedido en Kafka para registro
        print("Pedido confirmado")

        # 4. Actualizar inventario
        for item in cart_items:
            inventory_update = {"product_id": item["product_id"], "quantity": -item["quantity"]}
            producer.send("inventory-updates", inventory_update)
        producer.flush()
        print("Solicitudes de actualización de inventario enviadas a Kafka.")

        return jsonify({"message": "Pedido creado exitosamente.", "order_id": order_id}), 201


    except Exception as e:
        error_message = f"Error al crear pedido: {str(e)}"
        print(error_message)
        return jsonify({"message": error_message}), 500


# 5.2 Listar pedidos del usuario
@app.route('/api/orders', methods=['GET'])
def list_orders():
    None

# 5.3 Obtener detalles de un pedido
@app.route('/api/orders/<int:order_id>', methods=['GET'])
def get_order_details(order_id):
    None

# 5.4 Cancelar un pedido
@app.route('/api/orders/<int:order_id>/cancel', methods=['POST'])
def cancel_order(order_id):
    None

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000,debug=True)
