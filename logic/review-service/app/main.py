from flask import Flask, jsonify, request, abort

app = Flask(__name__)


# 6.1 Listar reseñas de un producto
@app.route('/api/products/<int:product_id>/reviews', methods=['GET'])
def list_reviews(product_id):
    None

# 6.2 Agregar una reseña a un producto
@app.route('/api/products/<int:product_id>/reviews', methods=['POST'])
def add_review(product_id):
    None

# 6.3 Actualizar una reseña
@app.route('/api/products/<int:product_id>/reviews/<int:review_id>', methods=['PUT'])
def update_review(product_id, review_id):
    None

# 6.4 Eliminar una reseña
@app.route('/api/products/<int:product_id>/reviews/<int:review_id>', methods=['DELETE'])
def delete_review(product_id, review_id):
    None

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
