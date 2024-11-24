from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSON
from datetime import datetime
import uuid 
from kafka import KafkaProducer
import json



app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:12345@localhost:5432/petstore'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Inicializo SQLAlchemy
db = SQLAlchemy(app)

producer = KafkaProducer(
    bootstrap_servers='mi-kafka.default.svc.cluster.local:9092',
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)


# 2.1 Listar categorías
@app.route('/api/categories', methods=['GET'])
def list_categories():
    try:
        # Parámetros de consulta
        query_param = request.args.get('q', '').strip() 
        parent_category = request.args.get('parent') 
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 10))
        offset = (page - 1) * limit

        # Construir consulta
        query = Category.query

        if query_param:
            query = query.filter(Category.name.ilike(f'%{query_param}%'))
        if parent_category:
            query = query.filter_by(parent_category=parent_category)

        # Paginación
        total_categories = query.count()
        categories = query.offset(offset).limit(limit).all()

        # Transformar resultados a JSON
        categories_list = [
            {
                'id': str(category.id),
                'name': category.name,
                'description': category.description,
                'parent_category': str(category.parent_category) if category.parent_category else None,
                'image_url': category.image_url,
                'active': category.active,
                'created_at': category.created_at,
            }
            for category in categories
        ]

        
        producer.send('search-updates', {'type': 'category', 'data': categories_list})

        return jsonify({
            'categories': categories_list,
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
