from flask import Flask, jsonify, request
from kafka import KafkaConsumer
import threading
import json

app = Flask(__name__)

# Almacenamiento temporal para datos recibidos
products = []
categories = []

# Consumidor de Kafka
def consume_kafka():
    consumer = KafkaConsumer(
        'search-updates',
        bootstrap_servers='mi-kafka.default.svc.cluster.local:9092',
        auto_offset_reset='earliest',
        enable_auto_commit=True,
        group_id='search-service',
        value_deserializer=lambda x: json.loads(x.decode('utf-8'))
    )

    for message in consumer:
        data = message.value
        if data['type'] == 'product':
            products.extend(data['data'])
            print("Productos recibidos:", products)
        elif data['type'] == 'category':
            categories.extend(data['data'])
            print("Categorías recibidas:", categories)

# Lanza el consumidor en un hilo
thread = threading.Thread(target=consume_kafka)
thread.daemon = True
thread.start()

# Endpoint de búsqueda
@app.route('/api/search', methods=['GET'])
def search():
    query = request.args.get('q', '').lower()
    product_results = [
        product for product in products
        if query in product['name'].lower() or query in product['description'].lower()
    ]
    category_results = [
        category for category in categories
        if query in category['name'].lower() or query in category['description'].lower()
    ]

    return jsonify({
        'products': product_results,
        'categories': category_results
    }), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
