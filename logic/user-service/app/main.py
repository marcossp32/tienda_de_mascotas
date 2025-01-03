from flask import Flask, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
import datetime
import uuid  
from functools import wraps
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
import logging
import os
from kafka import KafkaProducer, KafkaConsumer
import threading
import sys
import json

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

app = Flask(__name__)

# Configuración de la base de datos y SQLAlchemy desde la variable de entorno DATABASE_URL
database_url = os.getenv("DATABASE_URL", "postgresql://postgres:12345@postgres-service.default.svc.cluster.local:5432/petstore")
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Configuración de clave secreta para JWT
SECRET_KEY = os.getenv("SECRET_KEY", "supersecretkey")

KAFKA_BROKER = os.getenv("KAFKA_BROKER", "localhost:9092")
producer = KafkaProducer(
    bootstrap_servers=KAFKA_BROKER,
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

# Función para crear token JWT
def create_jwt_token(user_id):
    token = jwt.encode({
        'user_id': user_id,
        'exp': datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=24)
    }, app.config['SECRET_KEY'], algorithm="HS256")
    return token


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None

        # Verificar si el token está presente en el encabezado Authorization
        if 'Authorization' in request.headers:
            try:
                auth_header = request.headers['Authorization']
                token = auth_header.split(" ")[1]  # Extraer el token después de "Bearer"
            except IndexError:
                return jsonify({'message': 'Formato del token inválido'}), 401

        if not token:
            return jsonify({'message': 'Token faltante'}), 401

        try:
            # Decodificar el token
            data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            request.user_id = data['user_id']  # Pasar user_id al contexto de la solicitud
        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'Token expirado'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'message': 'Token inválido'}), 401

        return f(*args, **kwargs)

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



# 3.5 Listar direcciones de envío con filtro de user_id
@app.route('/api/users/addresses', methods=['GET'])
@token_required
def list_addresses():
    try:
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({"message": "El campo 'user_id' es obligatorio."}), 400

        # Consultar direcciones del usuario
        query = """
        SELECT id, street, city, state, country, zip_code, is_default
        FROM addresses
        WHERE user_id = :user_id
        """
        params = {"user_id": user_id}
        addresses = db.session.execute(query, params).fetchall()

        if not addresses:
            return jsonify({"message": "No se encontraron direcciones."}), 404

        # Ajustar para acceder con índices
        response = [{
            "address_id": str(row[0]),
            "street": row[1],
            "city": row[2],
            "state": row[3],
            "country": row[4],
            "zip_code": row[5],
            "is_default": row[6]
        } for row in addresses]

        return jsonify(response), 200

    except Exception as e:
        print(f"Error al listar direcciones: {e}")
        return jsonify({"message": f"Error interno: {str(e)}"}), 500



# Consumidor de Kafka para solicitudes de direcciones
def consume_address_requests():
    try:
        consumer = KafkaConsumer(
            "address-requests",
            bootstrap_servers=KAFKA_BROKER,
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),
            group_id="user-service",
            auto_offset_reset="latest",
        )
        print("Iniciando consumo del tópico 'address-requests'")

        for message in consumer:
            data = message.value
            user_id = data.get("user_id")
            token = data.get("token")

            # Crear encabezados para simular la solicitud
            headers = {
                'Authorization': f'Bearer {token}'
            }

            with app.test_request_context(f"/api/users/addresses?user_id={user_id}", headers=headers):
                response = list_addresses()
                status_code = response[1]

                if status_code == 200:
                    address = response[0].get_json()
                    producer.send("address-responses", address)
                    producer.flush()
                    print(f"Respuesta de dirección publicada en Kafka: {address}")
                else:
                    print(f"Error al consultar addresses: {status_code}")

    except Exception as e:
        print(f"Error: {e}")



# Iniciar consumidor en un hilo separado
threading.Thread(target=consume_address_requests, daemon=True).start()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000,debug=True)
