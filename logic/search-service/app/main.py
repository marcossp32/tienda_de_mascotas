from flask import Flask, jsonify, request
from kafka import KafkaConsumer
import threading
import json
import os
from flask_cors import CORS
import random

app = Flask(__name__)
CORS(app)

# Almacenamiento temporal solo para lo que llega del 'search-topic'
search_results = []

# Consumidor de Kafka
class PageViewKafkaConsumer:
    def __init__(self, topic: str, group_prefix: str = 'pageview-group'):
        self.topic = topic
        self.consumer = KafkaConsumer(
            topic,
            auto_offset_reset='latest',
            group_id=f"{group_prefix}-{random.randrange(99999)}",
            bootstrap_servers=os.getenv("KAFKA_BROKER", "localhost:9092"),
            value_deserializer=lambda x: json.loads(x.decode('utf-8'))
        )

    def consume_messages(self):
        print(f"Iniciando consumidor de Kafka para el tópico '{self.topic}'...")
        for message in self.consumer:
            print(f"""
                {message.topic}:{message.partition}:{message.offset}
                key={message.key} value={message.value}
            """)
            data = message.value
            
            # Solo procesar lo que llega del 'search-topic'
            if self.topic == 'search-topic':
                if 'data' in data:
                    print("Datos procesados desde Kafka:", data['data'])
                    search_results.extend(data['data'])


# Iniciar consumidor para 'search-topic'
def start_kafka_consumers():
    search_consumer = PageViewKafkaConsumer('search-topic', group_prefix='search-service')
    threading.Thread(target=search_consumer.consume_messages, daemon=True).start()

start_kafka_consumers()

@app.route('/api/search', methods=['GET'])
def search():
    """
    Endpoint que filtra datos que llegaron del tópico 'search-topic' 
    según el parámetro de búsqueda 'q'.
    """
    query = request.args.get('q', '').lower()
    print(f"Filtrando resultados para la query: '{query}'")
    
    # Filtrar sobre los datos recibidos del tópico 'search-topic'
    filtered_results = [item for item in search_results if query in item.get('name', '').lower()]
    
    return jsonify({'results': filtered_results}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002)
