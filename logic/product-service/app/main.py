from flask import Flask, jsonify, request, abort

app = Flask(__name__)


# 1.1 Listar productos
@app.route('/api/products', methods=['GET'])
def list_products():
    return "Hola mundo, estas en products"


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
