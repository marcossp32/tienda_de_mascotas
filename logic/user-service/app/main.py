from flask import Flask, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
import datetime
from functools import wraps
from database.create_tables import db, User,Address
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
import os


app = Flask(__name__)
CORS(app)

# Configuración de la base de datos y SQLAlchemy
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URL")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False 
db = SQLAlchemy(app)

# Configuración de clave secreta para JWT
app.config['SECRET_KEY'] = 'supersecretkey'

# Función para crear token JWT
def create_jwt_token(user_id):
    token = jwt.encode({
        'user_id': user_id,
        'exp': datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=24)  # Expiración en 24 horas
    }, app.config['SECRET_KEY'], algorithm="HS256")
    return token

# Decorador para verificar el token JWT en rutas protegidas
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('x-access-token')
        if not token:
            return jsonify({'message': 'Token es requerido'}), 401
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = User.query.filter_by(id=data['user_id']).first()
            if not current_user:
                return jsonify({'message': 'Token inválido'}), 401
        except Exception as e:
            return jsonify({'message': f'Token inválido o expirado: {str(e)}'}), 401
        return f(current_user, *args, **kwargs)
    return decorated

# 3.1 Registrar un nuevo usuario
@app.route('/api/users/register', methods=['POST'])
def register():
    data = request.get_json()

    if not data or not 'username' in data or not 'password' in data or not 'email' in data:
        return jsonify({'message': 'Faltan datos'}), 400

    username = data['username']
    email = data['email']
    password = data['password']

    existing_user = User.query.filter((User.username == username) | (User.email == email)).first()
    if existing_user:
        return jsonify({'message': 'El usuario o el correo ya existe'}), 400

    hashed_password = generate_password_hash(password)
    new_user = User(
        id=str(datetime.datetime.now(datetime.timezone.utc).timestamp()),
        username=username,
        email=email,
        password=hashed_password,
        first_name=data.get('firstName', ''),
        last_name=data.get('lastName', ''),
        phone_number=data.get('phoneNumber', ''),
        created_at=datetime.datetime.now(datetime.timezone.utc)
    )

    db.session.add(new_user)
    db.session.commit()
    
    token = create_jwt_token(new_user.id)

    return jsonify({'message': 'Usuario registrado con éxito', 'token': token}), 201


# 3.2 Iniciar sesión
@app.route('/api/users/login', methods=['POST'])
def login():
    data = request.get_json()
    
    if not data or not 'username' in data or not 'password' in data:
        return jsonify({'message': 'Faltan datos'}), 400

    username = data['username']
    password = data['password']
    
    try:
        
        user = User.query.filter_by(username=username).first()
        
        # Revisa si el usuario fue encontrado y si la contraseña coincide
        if not user or not check_password_hash(user.password, password):
            return jsonify({'message': 'Usuario o contraseña incorrectos'}), 401

        token = create_jwt_token(user.id)
        return jsonify({'message': 'Inicio de sesión exitoso', 'token': token}), 200
    except Exception as e:
        return jsonify({'message': 'Error interno en el servidor'}), 500


# 3.3 y 3.4 Obtener y Actualizar perfil de usuario
@app.route('/api/users/profile', methods=['GET', 'PUT'])
@token_required
def perfil_usuario(current_user):
    if request.method == 'GET':
        # Retornar los datos del perfil del usuario
        user_data = {
            'username': current_user.username,
            'email': current_user.email,
            'firstName': current_user.first_name,
            'lastName': current_user.last_name,
            'phoneNumber': current_user.phone_number,
        }
        return jsonify({'profile': user_data}), 200
    elif request.method == 'PUT':
        data = request.get_json()
        current_user.first_name = data.get('firstName', current_user.first_name)
        current_user.Addresslast_name = data.get('lastName', current_user.last_name)
        current_user.phone_number = data.get('phoneNumber', current_user.phone_number)
        db.session.commit()
        return jsonify({'message': 'Perfil actualizado con éxito'}), 200

# 3.5 Listar direcciones de envío
@app.route('/api/users/addresses', methods=['GET'])
@token_required
def listar_direcciones(current_user):
    addresses = Address.query.filter_by(user_id=current_user.id).all()
    addresses_list = [
        {
            'street': address.street,
            'city': address.city,
            'state': address.state,
            'country': address.country,
            'zipCode': address.zip_code,
            'isDefault': address.is_default
        } for address in addresses
    ]
    return jsonify({'addresses': addresses_list}), 200

# 3.6 Agregar dirección de envío
@app.route('/api/users/addresses', methods=['POST'])
@token_required
def agregar_direcciones(current_user):
    data = request.get_json()
    new_address = Address(
        id=str(datetime.datetime.now(datetime.timezone.utc).timestamp()),  # ID único
        user_id=current_user.id,
        street=data['street'],
        city=data['city'],
        state=data.get('state', ''),
        country=data['country'],
        zip_code=data['zipCode'],
        is_default=data.get('isDefault', False)
    )
    db.session.add(new_address)
    db.session.commit()
    return jsonify({'message': 'Dirección agregada con éxito'}), 201

# 3.7 Actualizar dirección de envío
@app.route('/api/users/addresses/<addressId>', methods=['PUT'])
@token_required
def actualizar_direcciones(current_user, addressId):
    address = Address.query.filter_by(id=addressId, user_id=current_user.id).first()
    if not address:
        return jsonify({'message': 'Dirección no encontrada'}), 404

    data = request.get_json()
    address.street = data.get('street', address.street)
    address.city = data.get('city', address.city)
    address.state = data.get('state', address.state)
    address.country = data.get('country', address.country)
    address.zip_code = data.get('zipCode', address.zip_code)
    address.is_default = data.get('isDefault', address.is_default)
    db.session.commit()
    return jsonify({'message': 'Dirección actualizada con éxito'}), 200

# 3.8 Eliminar dirección de envío
@app.route('/api/users/addresses/<addressId>', methods=['DELETE'])
@token_required
def eliminar_direcciones(current_user, addressId):
    address = Address.query.filter_by(id=addressId, user_id=current_user.id).first()
    if not address:
        return jsonify({'message': 'Dirección no encontrada'}), 404

    db.session.delete(address)
    db.session.commit()
    return jsonify({'message': 'Dirección eliminada con éxito'}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

