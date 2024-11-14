from flask import Flask, jsonify, request, abort

app = Flask(__name__)


# 4.1 Obtener carrito actual
@app.route('/api/cart', methods=['GET'])
def get_cart():
    None

# 4.2 Agregar producto al carrito
@app.route('/api/cart/items', methods=['POST'])
def add_to_cart():
    None

# 4.3 Actualizar cantidad de un producto en el carrito
@app.route('/api/cart/items/<int:item_id>', methods=['PUT'])
def update_cart_item(item_id):
    None

# 4.4 Eliminar producto del carrito
@app.route('/api/cart/items/<int:item_id>', methods=['DELETE'])
def delete_cart_item(item_id):
    None

# 4.5 Vaciar carrito
@app.route('/api/cart', methods=['DELETE'])
def clear_cart():
    None

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
