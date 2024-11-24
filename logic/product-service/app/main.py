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

# 1.1 Listar productos
@app.route('/api/products', methods=['GET'])
def list_products():
    try:
        # Parámetros de consulta
        category = request.args.get('category')  
        animal_type = request.args.get('animalType')  
        price_min = request.args.get('priceMin', type=float)  
        price_max = request.args.get('priceMax', type=float)  
        tag = request.args.get('tag')  
        order_by = request.args.get('orderBy', 'created_at')
        order_dir = request.args.get('orderDir', 'desc') 
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 10))
        offset = (page - 1) * limit

        # Construir consulta
        query = Product.query

        if category:
            query = query.filter_by(category=category)
        if animal_type:
            query = query.filter(Product.animal_type.ilike(f'%{animal_type}%'))
        if price_min is not None:
            query = query.filter(Product.price >= price_min)
        if price_max is not None:
            query = query.filter(Product.price <= price_max)
        if tag:
            query = query.filter(Product.tags.any(tag))

        # Ordenación
        if order_dir.lower() == 'desc':
            query = query.order_by(db.desc(getattr(Product, order_by, 'created_at')))
        else:
            query = query.order_by(getattr(Product, order_by, 'created_at'))

        # Paginación
        total_products = query.count()
        products = query.offset(offset).limit(limit).all()

        # Transformar resultados a JSON
        products_list = [
            {
                'id': str(product.id),
                'name': product.name,
                'description': product.description,
                'price': product.price,
                'category': str(product.category),
                'animal_type': product.animal_type,
                'brand': product.brand,
                'stock': product.stock,
                'images': product.images,
                'specifications': product.specifications,
                'tags': product.tags,
                'average_rating': product.average_rating,
                'created_at': product.created_at,
                'updated_at': product.updated_at,
            }
            for product in products
        ]

        producer.send('search-updates', {'type': 'product', 'data': products_list})

        return jsonify({
            'products': products_list,
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
