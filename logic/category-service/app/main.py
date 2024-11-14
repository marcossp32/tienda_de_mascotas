from flask import Flask, jsonify, request, abort

app = Flask(__name__)

# 2.1 Listar categorías
@app.route('/api/categories', methods=['GET'])
def list_categories():
    None

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
