from flask import Flask, jsonify, request, abort

app = Flask(__name__)

# 5.1 Crear un nuevo pedido
@app.route('/api/orders', methods=['POST'])
def create_order():
    None

# 5.2 Listar pedidos del usuario
@app.route('/api/orders', methods=['GET'])
def list_orders():
    None

# 5.3 Obtener detalles de un pedido
@app.route('/api/orders/<int:order_id>', methods=['GET'])
def get_order_details(order_id):
    None

# 5.4 Cancelar un pedido
@app.route('/api/orders/<int:order_id>/cancel', methods=['POST'])
def cancel_order(order_id):
    None

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
