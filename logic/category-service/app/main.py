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

# Listar categorías
@app.route('/api/categories', methods=['GET'])
def list_categories():
    try:
        query_param = request.args.get('q', '').strip()
        parent_category = request.args.get('parent')
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 10))
        offset = (page - 1) * limit

        # Construir consulta
        base_query = """
        SELECT id, name, description, parent_category, image_url, active
        FROM categories
        WHERE 1=1
        """
        filters = []
        params = {}

        if query_param:
            filters.append("name ILIKE :query_param")
            params['query_param'] = f"%{query_param}%"
        if parent_category:
            filters.append("parent_category = :parent_category")
            params['parent_category'] = parent_category

        if filters:
            base_query += " AND " + " AND ".join(filters)

        base_query += " LIMIT :limit OFFSET :offset"
        params.update({'limit': limit, 'offset': offset})

        # Consultar la base de datos
        result = db.session.execute(base_query, params).fetchall()

        # Transformar resultados
        categories = [{
            'id': str(row['id']),
            'name': row['name'],
            'description': row['description'],
            'parent_category': str(row['parent_category']) if row['parent_category'] else None,
            'image_url': row['image_url'],
            'active': row['active'],
        } for row in result]

        # Total de categorías
        count_query = f"SELECT COUNT(*) FROM categories WHERE 1=1 {' AND '.join(filters) if filters else ''}"
        total_categories = db.session.execute(count_query, params).scalar()

        # Enviar datos de categorías a Kafka
        producer.send('search-topic', {'type': 'category', 'data': categories})
        producer.flush()

        # Loguear PageView
        pageview = PageView(f"/api/categories?page={page}&limit={limit}&q={query_param}&parent={parent_category}")
        pageview_logger.produce(pageview)

        return jsonify({
            'categories': categories,
            'total': total_categories,
            'page': page,
            'limit': limit
        }), 200

    except Exception as e:
        return jsonify({'message': f'Error al listar categorías: {str(e)}'}), 500

# 2.2 Obtener detalles de una categoría
@app.route('/api/categories/<int:category_id>', methods=['GET'])
def get_category_details(category_id):
    None

# 2.3 Crear una nueva categoría (admin)
@app.route('/api/categories', methods=['POST'])
def create_category():
    None

# 2.4 Actualizar una categoría (admin)
@app.route('/api/categories/<int:category_id>', methods=['PUT'])
def update_category(category_id):
    None

# 2.5 Eliminar una categoría (admin)
@app.route('/api/categories/<int:category_id>', methods=['DELETE'])
def delete_category(category_id):
    None

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
