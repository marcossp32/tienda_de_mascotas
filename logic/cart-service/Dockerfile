# Usa una imagen base ligera de Python
FROM python:3.10-slim

# Establece el directorio de trabajo en el contenedor
WORKDIR /app

# Copia los archivos del servicio al contenedor
COPY . /app

# Instala las dependencias desde requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Expone el puerto en el que correrá el microservicio Flask
EXPOSE 5000

# Comando para ejecutar el servicio
CMD ["python", "app/main.py"]
