from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from kafka import KafkaProducer
import os
import json
import random

# Configurar la app Flask
app = Flask(__name__)
CORS(app)

# Configuración de la base de datos
database_url = os.getenv("DATABASE_URL", "postgresql://postgres:12345@postgres-service.default.svc.cluster.local:5432/petstore")
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Configuración del productor de Kafka
producer = KafkaProducer(
    bootstrap_servers=os.getenv("KAFKA_BROKER", "kafka.default.svc.cluster.local:9092"),
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

# Clase PageView
class PageView:
    def __init__(self, url: str):
        self._url = url

    @property
    def url(self):
        return self._url

    def to_json(self):
        return json.dumps({"pageview": {"url": self.url}})

# Clase PageViewKafkaLogger
class PageViewKafkaLogger:
    def __init__(self, broker: str = 'kafka.default.svc.cluster.local:9092'):
        self.producer = KafkaProducer(
            bootstrap_servers=broker,
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )

    def produce(self, pageview: PageView):
        try:
            # Enviar un mensaje al tópico 'pageview'
            self.producer.send(
                topic='pageview',
                key=f"{random.randrange(999999)}".encode(),
                value=json.loads(pageview.to_json())
            )
            self.producer.flush()
        except Exception as e:
            print(f"Error enviando PageView a Kafka: {e}")

pageview_logger = PageViewKafkaLogger()

# Listar productos
@app.route('/api/products', methods=['GET'])
def list_products():
    try:
        # Obtener parámetros
        category = request.args.get('category')
        price_min = request.args.get('priceMin', type=float)
        price_max = request.args.get('priceMax', type=float)
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 10))
        offset = (page - 1) * limit

        # Construir la consulta SQL
        base_query = """
        SELECT id, name, description, price, category, stock, images, created_at, updated_at
        FROM products
        WHERE 1=1
        """
        filters = []
        params = {}

        if category:
            filters.append("category = :category")
            params['category'] = category
        if price_min:
            filters.append("price >= :price_min")
            params['price_min'] = price_min
        if price_max:
            filters.append("price <= :price_max")
            params['price_max'] = price_max

        if filters:
            base_query += " AND " + " AND ".join(filters)

        base_query += " LIMIT :limit OFFSET :offset"
        params.update({'limit': limit, 'offset': offset})

        # Consultar la base de datos
        result = db.session.execute(base_query, params).fetchall()

        # Procesar resultados
        products = [{
            'id': str(row['id']),
            'name': row['name'],
            'description': row['description'],
            'price': row['price'],
            'category': str(row['category']),
            'stock': row['stock'],
            'images': row['images'],
            'created_at': row['created_at'].isoformat(),
            'updated_at': row['updated_at'].isoformat()
        } for row in result]

        # Total de productos
        count_query = f"SELECT COUNT(*) FROM products WHERE 1=1 {' AND '.join(filters) if filters else ''}"
        total_products = db.session.execute(count_query, params).scalar()

        # Enviar datos de productos a Kafka
        producer.send('search-topic', {'type': 'product', 'data': products})
        print(f"Enviado a search-topic: {products}")
        producer.flush()

        # Loguear PageView
        pageview = PageView(f"/api/products?page={page}&limit={limit}&category={category}")
        pageview_logger.produce(pageview)

        return jsonify({
            'products': products,
            'total': total_products,
            'page': page,
            'limit': limit
        }), 200

    except Exception as e:
        return jsonify({'message': f'Error al listar productos: {str(e)}'}), 500


# 1.2 Obtener detalles de un producto
@app.route('/api/products/<int:productId>', methods=['GET'])
def get_product(productId):
    None


# 1.3 Crear un nuevo producto (admin)
@app.route('/api/products', methods=['POST'])
def create_product():
    None


# 1.4 Actualizar un producto (admin)
@app.route('/api/products/<int:productId>', methods=['PUT'])
def update_product(productId):
    None


# 1.5 Eliminar un producto (admin)
@app.route('/api/products/<int:productId>', methods=['DELETE'])
def delete_product(productId):
    None


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
