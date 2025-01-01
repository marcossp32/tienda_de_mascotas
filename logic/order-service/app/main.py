from flask import Flask, jsonify, request
from kafka import KafkaProducer, KafkaConsumer
import threading
import json
import uuid
from datetime import datetime
import os

app = Flask(__name__)

# Configuración de Kafka
KAFKA_BROKER = os.getenv("KAFKA_BROKER", "localhost:9092")
producer = KafkaProducer(
    bootstrap_servers=KAFKA_BROKER,
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

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

        address_response = []
        address_event = threading.Event()

        def consume_address_response():
            consumer = KafkaConsumer(
                "address-responses",
                bootstrap_servers=KAFKA_BROKER,
                value_deserializer=lambda x: json.loads(x.decode('utf-8')),
                group_id="order-service",
                auto_offset_reset="earliest",
            )
            for message in consumer:
                data = message.value
                if data.get("user_id") == user_id:
                    address_response.append(data.get("address"))
                    address_event.set()
                    break

        threading.Thread(target=consume_address_response, daemon=True).start()

        if not address_event.wait(timeout=5):
            return jsonify({"message": "Timeout al obtener la dirección del usuario."}), 500

        if not address_response:
            return jsonify({"message": "No se encontró dirección para el usuario."}), 404

        shipping_address = address_response[0]

        # 2. Solicitar ítems del carrito
        producer.send("cart-items-requests", {"user_id": user_id})
        producer.flush()
        print(f"Solicitud de ítems del carrito enviada a Kafka para user_id {user_id}")

        cart_items_response = []
        cart_event = threading.Event()

        def consume_cart_items_response():
            consumer = KafkaConsumer(
                "cart-responses",
                bootstrap_servers=KAFKA_BROKER,
                value_deserializer=lambda x: json.loads(x.decode('utf-8')),
                group_id="order-service",
                auto_offset_reset="earliest",
            )
            for message in consumer:
                data = message.value
                if data.get("user_id") == user_id:
                    cart_items_response.append(data.get("response"))
                    cart_event.set()
                    break

        threading.Thread(target=consume_cart_items_response, daemon=True).start()

        if not cart_event.wait(timeout=5):
            return jsonify({"message": "Timeout al obtener ítems del carrito."}), 500

        cart_response = cart_items_response[0]

        if "items" not in cart_response or not cart_response["items"]:
            return jsonify({"message": "No se encontraron ítems en el carrito."}), 404

        cart_items = cart_response["items"]

        # 3. Crear pedido
        total_amount = sum(item["quantity"] * item["price"] for item in cart_items)
        order_id = str(uuid.uuid4())
        order = {
            "id": order_id,
            "user_id": user_id,
            "total_amount": total_amount,
            "shipping_address": shipping_address,
            "payment_method": payment_method,
            "status": "Pending",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "items": cart_items
        }

        # Publicar el pedido en Kafka para registro
        producer.send("orders", order)
        producer.flush()
        print(f"Pedido creado y publicado en Kafka: {order}")

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
    app.run(host='0.0.0.0', port=5000)
