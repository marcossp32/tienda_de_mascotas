from flask import Flask, jsonify, request, abort

app = Flask(__name__)

# Simulación de base de datos en memoria
users = []
addresses = []

# 3.1 Registrar un nuevo usuario
@app.route('/api/users/register', methods=['POST'])
def register_user():
    return "Hola mundo, estas en register"

# 3.2 Iniciar sesión
@app.route('/api/users/login', methods=['POST'])
def login_user():
    None

# 3.3 Obtener perfil de usuario
@app.route('/api/users/profile', methods=['GET'])
def get_user_profile():
    None

# 3.4 Actualizar perfil de usuario
@app.route('/api/users/profile', methods=['PUT'])
def update_user_profile():
    None

# 3.5 Listar direcciones de envío
@app.route('/api/users/addresses', methods=['GET'])
def list_addresses():
    None

# 3.6 Agregar dirección de envío
@app.route('/api/users/addresses', methods=['POST'])
def add_address():
    None

# 3.7 Actualizar dirección de envío
@app.route('/api/users/addresses/<int:address_id>', methods=['PUT'])
def update_address(address_id):
    None

# 3.8 Eliminar dirección de envío
@app.route('/api/users/addresses/<int:address_id>', methods=['DELETE'])
def delete_address(address_id):
    None

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
