from flask import Flask, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
import datetime
import uuid  # Para generar UUIDs
from functools import wraps
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
import logging
import os

app = Flask(__name__)
CORS(app)

# Configuración de la base de datos y SQLAlchemy desde la variable de entorno DATABASE_URL
database_url = os.getenv("DATABASE_URL", "postgresql://postgres:12345@localhost:5432/petstore")
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Configuración de clave secreta para JWT
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "supersecretkey")

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
            # Decodificar el token JWT
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            user_id = data.get('user_id')

            # Verificar si el usuario existe en la base de datos
            current_user = db.session.execute(
                "SELECT id, username, email FROM users WHERE id = :user_id",
                {'user_id': user_id}
            ).fetchone()

            if not current_user:
                return jsonify({'message': 'Token inválido'}), 401

        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'El token ha expirado'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'message': 'Token inválido'}), 401
        except Exception as e:
            return jsonify({'message': f'Error procesando el token: {str(e)}'}), 401

        # Pasar el usuario actual como argumento a la función protegida
        return f(current_user, *args, **kwargs)
    return decorated

# 3.1 Registrar un nuevo usuario
@app.route('/api/users/register', methods=['POST'])
def register_user():
    data = request.get_json()

    # Validar entrada
    if not data or not 'username' in data or not 'password' in data or not 'email' in data:
        return jsonify({'message': 'Faltan datos'}), 400

    username = data['username']
    email = data['email']
    password = data['password']

    # Verificar si el usuario o email ya existen
    existing_user = db.session.execute(
        "SELECT * FROM users WHERE username = :username OR email = :email",
        {'username': username, 'email': email}
    ).fetchone()

    if existing_user:
        return jsonify({'message': 'El usuario o el correo ya existe'}), 400

    # Crear nuevo usuario
    hashed_password = generate_password_hash(password)
    user_id = str(uuid.uuid4())  # Generar un UUID válido
    created_at = datetime.datetime.now(datetime.timezone.utc)

    db.session.execute(
    "INSERT INTO users (id, username, email, password, first_name, last_name, phone_number, created_at, role) "
    "VALUES (:id, :username, :email, :password, :first_name, :last_name, :phone_number, :created_at, :role)",
        {
            'id': user_id,
            'username': username,
            'email': email,
            'password': hashed_password,
            'first_name': data.get('firstName', ''),
            'last_name': data.get('lastName', ''),
            'phone_number': data.get('phoneNumber', ''),
            'created_at': created_at,
            'role': 'user',  # Por defecto lo dejo en user
        }
    )
    db.session.commit()


    # Crear y devolver token JWT
    token = create_jwt_token(user_id)
    return jsonify({'message': 'Usuario registrado con éxito', 'token': token}), 201

# 3.2 Iniciar sesión
@app.route('/api/users/login', methods=['POST'])
def login_user():
    try:
        data = request.get_json()

        if not data or not 'username' in data or not 'password' in data:
            return jsonify({'message': 'Faltan datos'}), 400

        username = data['username']
        password = data['password']

        # Buscar usuario por nombre
        user = db.session.execute(
            "SELECT * FROM users WHERE username = :username",
            {'username': username}
        ).fetchone()

        if not user:
            logging.debug("Usuario no encontrado")
            return jsonify({'message': 'Usuario o contraseña incorrectos'}), 401

        # Validar contraseña
        if not check_password_hash(user.password, password):
            logging.debug("Contraseña incorrecta")
            return jsonify({'message': 'Usuario o contraseña incorrectos'}), 401

        # Actualizar última conexión
        db.session.execute(
            "UPDATE users SET last_login = :last_login WHERE id = :user_id",
            {'last_login': datetime.datetime.now(datetime.timezone.utc), 'user_id': user.id}
        )
        db.session.commit()

        # Crear y devolver token JWT
        token = create_jwt_token(str(user.id))  # Convertir UUID a cadena
        return jsonify({'message': 'Inicio de sesión exitoso', 'token': token}), 200

    except Exception as e:
        logging.error(f"Error en el inicio de sesión: {str(e)}")
        return jsonify({'message': 'Error interno en el servidor'}), 500



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
