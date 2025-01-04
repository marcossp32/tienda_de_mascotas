from flask import Flask, request, jsonify
from kafka import KafkaProducer, KafkaConsumer
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from functools import wraps

import jwt
import datetime
import uuid  
import os
import threading
import sys
import json

# Configurar la salida estándar para manejar el buffering correctamente
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# Configuración de Flask
app = Flask(__name__)

# Configuración de la base de datos
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:12345@postgres-service.default.svc.cluster.local:5432/petstore")
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Configuración de Kafka
KAFKA_BROKER = os.getenv("KAFKA_BROKER", "localhost:9092")
producer = KafkaProducer(
    bootstrap_servers=KAFKA_BROKER,
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

# Clave secreta para JWT
SECRET_KEY = os.getenv("SECRET_KEY", "supersecretkey")
app.config['SECRET_KEY'] = SECRET_KEY

def create_jwt_token(user_id):
    """
    Crea un token JWT (JSON Web Token) para un usuario específico.

    Este token incluye:
    - `user_id`: Identificador único del usuario.
    - `exp`: Tiempo de expiración del token, que en este caso es 24 horas desde el momento de su creación.

    El token se firma con una clave secreta definida en la configuración de la aplicación (`app.config['SECRET_KEY']`)
    y utiliza el algoritmo HS256 para la firma.

    Args:
        user_id (str): El identificador único del usuario para incluir en el token.

    Returns:
        str: Un token JWT codificado que contiene el `user_id` y la fecha de expiración.
    """
    token = jwt.encode(
        {
            'user_id': user_id,
            'exp': datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=24)  # Expira en 24 horas
        },
        app.config['SECRET_KEY'],  # Clave secreta para firmar el token
        algorithm="HS256"  # Algoritmo de firma
    )
    return token


def token_required(f):
    """
    Decorador para proteger rutas mediante autenticación basada en tokens JWT.
    
    Este decorador asegura que las rutas protegidas solo puedan ser accedidas por usuarios 
    que envíen un token JWT válido en el encabezado `Authorization`. Si el token no es 
    válido o está ausente, se devuelve una respuesta con un código de estado HTTP apropiado.
    
    Args:
        f (function): La función que será decorada.

    Returns:
        function: La función decorada con validación de token.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None

        # Verificar si el token está presente en el encabezado Authorization
        if 'Authorization' in request.headers:
            try:
                # Extraer el encabezado Authorization y separar el token después de "Bearer"
                auth_header = request.headers['Authorization']
                token = auth_header.split(" ")[1]  
            except IndexError:
                # Si el formato del token es incorrecto
                return jsonify({'message': 'Formato del token inválido'}), 401

        # Si no hay token en el encabezado
        if not token:
            return jsonify({'message': 'Token faltante'}), 401

        try:
            # Decodificar el token utilizando la clave secreta y el algoritmo HS256
            data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            # Asignar el ID del usuario (user_id) al objeto request para su uso posterior
            request.user_id = data['user_id']
        except jwt.ExpiredSignatureError:
            # Si el token ha expirado
            return jsonify({'message': 'Token expirado'}), 401
        except jwt.InvalidTokenError:
            # Si el token no es válido
            return jsonify({'message': 'Token inválido'}), 401

        # Si el token es válido, proceder a ejecutar la función original
        return f(*args, **kwargs)

    return decorated

# Registrar un nuevo usuario
@app.route('/api/users/register', methods=['POST'])
def register_user():
    """
    Endpoint para registrar un nuevo usuario.

    Este endpoint permite registrar un nuevo usuario en el sistema. Valida los datos de entrada,
    verifica si el usuario o el correo ya existen, guarda al usuario en la base de datos y genera 
    un token JWT para autenticar al usuario recién creado.

    Returns:
        Response: Respuesta JSON con un mensaje de éxito o error, y un token JWT en caso de éxito.
    """
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
    hashed_password = generate_password_hash(password)  # Hashear la contraseña para mayor seguridad
    user_id = str(uuid.uuid4())  # Generar un UUID único para el usuario
    created_at = datetime.datetime.now(datetime.timezone.utc)  # Fecha y hora actual en UTC

    # Insertar el nuevo usuario en la base de datos
    db.session.execute(
        """
        INSERT INTO users (id, username, email, password, first_name, last_name, phone_number, created_at, role)
        VALUES (:id, :username, :email, :password, :first_name, :last_name, :phone_number, :created_at, :role)
        """,
        {
            'id': user_id,
            'username': username,
            'email': email,
            'password': hashed_password,
            'first_name': data.get('firstName', ''),  # Campo opcional
            'last_name': data.get('lastName', ''),    # Campo opcional
            'phone_number': data.get('phoneNumber', ''),  # Campo opcional
            'created_at': created_at,
            'role': 'user',  # Por defecto, el rol del usuario es 'user'
        }
    )
    db.session.commit()  # Confirmar los cambios en la base de datos

    # Crear y devolver token JWT
    token = create_jwt_token(user_id)  # Generar un token JWT para el nuevo usuario
    return jsonify({'message': 'Usuario registrado con éxito', 'token': token}), 201

# Iniciar sesión
@app.route('/api/users/login', methods=['POST'])
def login_user():
    """
    Endpoint para iniciar sesión de un usuario.

    Este endpoint permite a un usuario autenticarse en el sistema proporcionando su nombre de usuario
    y contraseña. Valida las credenciales y devuelve un token JWT para sesiones autenticadas.

    Returns:
        Response: Respuesta JSON con un mensaje de éxito o error, y un token JWT en caso de éxito.
    """
    try:
        # Obtener los datos enviados en la solicitud
        data = request.get_json()

        # Validar que los datos requeridos estén presentes
        if not data or not 'username' in data or not 'password' in data:
            return jsonify({'message': 'Faltan datos'}), 400

        username = data['username']
        password = data['password']

        # Buscar al usuario en la base de datos por su nombre de usuario
        user = db.session.execute(
            "SELECT * FROM users WHERE username = :username",
            {'username': username}
        ).fetchone()

        if not user:
            print("Usuario no encontrado")
            return jsonify({'message': 'Usuario o contraseña incorrectos'}), 401

        # Validar que la contraseña ingresada sea correcta
        if not check_password_hash(user.password, password):
            print("Contraseña incorrecta")
            return jsonify({'message': 'Usuario o contraseña incorrectos'}), 401

        # Actualizar la última conexión del usuario
        db.session.execute(
            "UPDATE users SET last_login = :last_login WHERE id = :user_id",
            {
                'last_login': datetime.datetime.now(datetime.timezone.utc),  # Fecha y hora actual en UTC
                'user_id': user.id
            }
        )
        db.session.commit()  # Confirmar los cambios en la base de datos

        # Crear y devolver un token JWT para el usuario
        token = create_jwt_token(str(user.id))  # Convertir el UUID a una cadena
        return jsonify({'message': 'Inicio de sesión exitoso', 'token': token}), 200

    except Exception as e:
        # Manejar errores internos y devolver un mensaje genérico
        print(f"Error en el inicio de sesión: {str(e)}")
        return jsonify({'message': 'Error interno en el servidor'}), 500



# Listar direcciones de envío con filtro de user_id
@app.route('/api/users/addresses', methods=['GET'])
@token_required
def list_addresses():
    """
    Endpoint para listar direcciones de envío de un usuario específico.

    Este endpoint permite a los usuarios autenticados obtener una lista de sus direcciones 
    de envío almacenadas en la base de datos. Se requiere el parámetro `user_id` en la 
    solicitud como filtro.

    Returns:
        Response: Respuesta JSON con las direcciones encontradas o un mensaje de error.
    """
    try:
        # Obtener el parámetro user_id de los argumentos de la solicitud
        user_id = request.args.get('user_id')
        if not user_id:
            # Si el user_id no está presente, devolver un mensaje de error
            return jsonify({"message": "El campo 'user_id' es obligatorio."}), 400

        # Consulta para obtener las direcciones asociadas al user_id
        query = """
        SELECT id, street, city, state, country, zip_code, is_default
        FROM addresses
        WHERE user_id = :user_id
        """
        params = {"user_id": user_id}
        addresses = db.session.execute(query, params).fetchall()

        # Verificar si se encontraron direcciones
        if not addresses:
            return jsonify({"message": "No se encontraron direcciones."}), 404

        # Construir la respuesta en formato JSON
        response = [{
            "address_id": str(row[0]),  # ID de la dirección
            "street": row[1],          # Calle
            "city": row[2],            # Ciudad
            "state": row[3],           # Estado
            "country": row[4],         # País
            "zip_code": row[5],        # Código postal
            "is_default": row[6]       # Indicador de dirección predeterminada
        } for row in addresses]

        # Devolver la lista de direcciones con un código de estado HTTP 200
        return jsonify(response), 200

    except Exception as e:
        # Manejar errores internos y devolver un mensaje genérico de error
        print(f"Error al listar direcciones: {e}")
        return jsonify({"message": f"Error interno: {str(e)}"}), 500



# Consumidor de Kafka para solicitudes de direcciones
def consume_address_requests():
    """
    Consumidor de Kafka para procesar solicitudes de direcciones de envío.

    Este consumidor escucha mensajes en el tópico `address-requests`, extrae la información
    necesaria para consultar las direcciones de un usuario y publica una respuesta en el
    tópico `address-responses`.

    Args:
        None

    Returns:
        None
    """
    try:
        # Configurar consumidor de Kafka
        consumer = KafkaConsumer(
            "address-requests",  # Tópico para escuchar solicitudes de direcciones
            bootstrap_servers=KAFKA_BROKER,
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),
            group_id="user-service",  # Grupo de consumidores
            auto_offset_reset="latest",  # Iniciar desde el último mensaje
        )
        print("Iniciando consumo del tópico 'address-requests'")

        for message in consumer:
            # Extraer datos del mensaje
            data = message.value
            user_id = data.get("user_id")  # ID del usuario
            token = data.get("token")  # Token JWT para autenticación

            # Crear encabezados para simular la solicitud HTTP
            headers = {
                'Authorization': f'Bearer {token}'  # Incluir el token en el encabezado
            }

            # Simular una solicitud al endpoint interno de direcciones
            with app.test_request_context(f"/api/users/addresses?user_id={user_id}", headers=headers):
                # Llamar al endpoint `list_addresses` directamente
                response = list_addresses()
                status_code = response[1]

                if status_code == 200:
                    # Si la solicitud fue exitosa, extraer datos y publicarlos en Kafka
                    address = response[0].get_json()
                    producer.send("address-responses", address)  # Publicar en el tópico
                    producer.flush()
                else:
                    # Imprimir error si no se pudo procesar correctamente
                    print(f"Error al consultar direcciones: {status_code}")

    except Exception as e:
        # Manejar errores en el consumidor
        print(f"Error: {e}")


# Iniciar consumidor en un hilo separado
threading.Thread(target=consume_address_requests, daemon=True).start()



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000,debug=True)
