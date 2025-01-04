
# API RESTful para Tienda de Mascotas

Este proyecto contiene las instrucciones necesarias para configurar y desplegar una API RESTful para una tienda de mascotas, utilizando herramientas como Docker, Minikube, Kafka y Kong.

## Documentación Adicional

- [Kong API Gateway - Ejemplo de Configuración](https://github.com/jlfg-evereven/ucjc-ida/blob/main/kong-api-gateway/README.md)
- [Documentación Oficial de Minikube con Kong](https://minikube.sigs.k8s.io/docs/handbook/addons/kong-ingress/)

## Instalación y Configuración

### Instalar Docker
```bash
sudo apt update
sudo apt install docker.io
sudo systemctl start docker
sudo systemctl enable docker
```

## Instalar Kubectl
```bash
sudo apt install -y apt-transport-https ca-certificates curl
sudo snap install kubectl --classic
kubectl version --client
```
## Instalar minikube
```bash
dpkg --print-architecture
curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64
sudo install minikube-linux-amd64 /usr/local/bin/minikube
minikube version
```

## Iniciar minikube
```bash
minikube start --driver=docker
```

## Configurar Docker con Minikube
```bash
eval $(minikube docker-env)
```

## Construcción de Imágenes
```bash
docker build -t cart-service:latest ./logic/cart-service
docker build -t category-service:latest ./logic/category-service
docker build -t order-service:latest ./logic/order-service
docker build -t product-service:latest ./logic/product-service
docker build -t review-service:latest ./logic/review-service
docker build -t search-service:latest ./logic/search-service
docker build -t user-service:latest ./logic/user-service
docker build -t postgres-service:latest ./database
```

## Aplicar la configuracion de kafka y zookeeper

```bash
kubectl apply -f kafka/kafka.yml
kubectl apply -f kafka/configMap.yml
kubectl apply -f kafka/kafka-topic-creator.yml
kubectl apply -f zookeeper/zookeeper.yml
```


## Aplicar Configuraciones en Kubernetes

### Primero se aplican los yml de la base de datos.
```bash
kubectl apply -f database/deployment.yml
kubectl apply -f database/service.yml
```

### Comprobamos que el pod creado esta en estado running
```bash
kubectl get pods
```

### Una vez veamos que el pod de postgres esta corriendo aplicamos los Job para crear las tablas e insertar datos a esas tablas y así poder hacer testeos
```bash
kubectl apply -f database/create-tables-job.yml
kubectl apply -f database/insert-data.yml
```

### Aplicamos todos los demás deployment y services de cada carpeta 
```bash
kubectl apply -f logic/cart-service/kube/
kubectl apply -f logic/category-service/kube/
kubectl apply -f logic/order-service/kube/
kubectl apply -f logic/product-service/kube/
kubectl apply -f logic/review-service/kube/
kubectl apply -f logic/search-service/kube/
kubectl apply -f logic/user-service/kube/
```

### Verificar Estado de los Pods y Servicios
```bash
kubectl get pods
kubectl get svc
```

### Si se quiere comprobar que las tablas han sido creadas y estan en el servicio de postgres, puedes usar \d para ver las tablas creadas
```bash
kubectl exec -it <pod de postgres> -- psql -U postgres -d petstore
```
Si ves que las tablas no han sido creadas es posible que hayas aplicado los job muy pronto por lo que se deberá borrar los jobs y aplicarlos de nuevo, para ello: 

```bash
kubectl delete job create-tables
kubectl delete job insert-data
```
y de nuevo:

```bash
kubectl apply -f database/create-tables-job.yml
kubectl apply -f database/insert-data.yml

```
## Instalación y Configuración de Kong en Kubernetes con Helm

#### Si no tienes helm instalado, se puede instalar ejecutando el archivo get_helm.sh

Darle permisos (chmod 700)

```bash
./get_helm.sh
```
#### Para instalar el repo la primera vez, usaremos helm

```bash
helm repo add kong https://charts.konghq.com && helm repo update
```

#### Una vez instalado, cada vez que se ha hecho minikube delete y se ha vuelto a empezar, habra que instalar esto:

```bash
helm install kong kong/kong --set ingressController.installCRDs=false && \ 
helm upgrade kong kong/kong --set admin.enabled=true --set admin.http.enabled=true
```

###  Comprobar que todo  esta correcto
```bash
 kubectl get pods
 kubectl get svc
```

###  Aplicar el ingress con las rutas para la API Gateway
```bash
kubectl apply -f kong/kong-ingress.yml
```

## Aplicar el host indicado

Obtenemos la ip:
```bash
minikube ip
```

Normalmente la ip de minikube es la misma, lo que se debe hacer ahora es colocar de esta manera [ ip , host que se ha aplicado en el ingress de kong ] en /etc/hosts
```bash
192.168.49.2   mini
```

Para acceder ahi:
```bash
sudo nano /etc/hosts
```

## Una vez hecho esto ya se pueden probar las rutas
#### Comprueba el puerto del kong proxy para realizar el curl
```bash
 kubectl get svc
```
#### Para las indicaciones se ha añadido < Y lo que hay que poner >, pero se debe poner sin los <> 

### Registro de un usuario
```bash
curl -X POST http://mini:<Puerto del kong proxy que apunta al 80>/api/users/register -H "Content-Type: application/json" -d '{
  "username": "prueba",
  "password": "12345",
  "email": "prueba@gmail.com",
  "firstName": "pruebaNombre",
  "lastName": "pruebaApellido",
  "phoneNumber": "123456789"
}'
```

### Debe devolver un mensaje como 
```json
{
  "message": "Usuario registrado con \u00e9xito", 
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiOWE4ZWMwNjktMGQ2My00ODkxLWEwZTMtMDM0ZDk4ODk5NjBkIiwiZXhwIjoxNzM2MDgwNTIyfQ.9sT30Ee348HRMi1J1LAhXtvFJ6haFa2YYxu5ethj_aw"
}
```

### Inicio de sesión
```bash
curl -X POST http://mini:<Puerto del kong proxy que apunta al 80>/api/users/login -H "Content-Type: application/json" -d '{
  "username": "prueba",
  "password": "12345"
}'
```
### Debe devolver un mensaje como 
```json
{
  "message": "Inicio de sesi\u00f3n exitoso", 
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiOWE4ZWMwNjktMGQ2My00ODkxLWEwZTMtMDM0ZDk4ODk5NjBkIiwiZXhwIjoxNzM2MDgwNTIyfQ.9sT30Ee348HRMi1J1LAhXtvFJ6haFa2YYxu5ethj_aw"
}
```

### Búsqueda de producto
```bash
curl -X GET "http://mini:<Puerto del kong proxy que apunta al 80>/api/search?q=perro" \
-H "Content-Type: application/json" \
-H "Authorization: Bearer <Token Jwt>"
```
### Debe devolver un mensaje como 
```json
{
  "categories": [
    {
      "data": [
        {
          "description": "Juguetes resistentes y divertidos para perros", 
          "id": "d43649ee-7f28-4eb2-a29c-09f2c5c5e2eb", 
          "image_url": "https://via.placeholder.com/32", 
          "name": "Juguetes para perros", 
          "parent_category": null
        }
      ], 
      "type": "category"
    }
  ], 
  "products": [
    {
      "data": [
        {
          "animal_type": "dog", 
          "average_rating": 4.5, 
          "brand": "DogFun", 
          "category": "d43649ee-7f28-4eb2-a29c-09f2c5c5e2eb", 
          "created_at": "2025-01-04T12:27:25.905731", 
          "description": "Pelota de goma ideal para juegos al aire libre.", 
          "id": "fbdc1a9f-cdf2-4963-bcbb-afbf2bf21316", 
          "images": [
            "https://via.placeholder.com/32", 
            "https://via.placeholder.com/32"
          ], 
          "name": "Pelota para perros", 
          "price": 10.99, 
          "specifications": {
            "material": "goma", 
            "tama\u00f1o": "mediano"
          }, 
          "stock": 50, 
          "tags": [
            "juguetes", 
            "perros"
          ], 
          "updated_at": "2025-01-04T12:27:25.905734"
        }
      ], 
      "type": "product"
    }
  ]
}
```
### Detalles del Producto
```bash
curl -X GET "http://mini:<Puerto del kong proxy que apunta al 80>/api/products/<Id del producto>" \
-H "Content-Type: application/json" \
-H "Authorization: Bearer <Token Jwt>"
```
### Debe devolver un mensaje como 
```json
{
  "product": {
    "category": "d43649ee-7f28-4eb2-a29c-09f2c5c5e2eb", 
    "created_at": "2025-01-04T12:27:25.905731", 
    "description": "Pelota de goma ideal para juegos al aire libre.", 
    "id": "fbdc1a9f-cdf2-4963-bcbb-afbf2bf21316", 
    "images": [
      "https://via.placeholder.com/32", 
      "https://via.placeholder.com/32"
    ], 
    "name": "Pelota para perros", 
    "price": 10.99, 
    "stock": 50, 
    "updated_at": "2025-01-04T12:27:25.905734"
  }, 
  "reviews_summary": {
    "average_rating": 5.0, 
    "helpful_votes": 10, 
    "total_reviews": 1
  }
}
```
### Reseñas del Producto
```bash
curl -X GET "http://mini:<Puerto del kong proxy que apunta al 80>/api/products/<Id del producto>/reviews" \
-H "Content-Type: application/json" \
-H "Authorization: Bearer <Token Jwt>"
```
### Debe devolver un mensaje como 
```json
{
  "reviews": [
    {
      "comment": "A mi perro le encant\u00f3, es muy resistente.", 
      "created_at": "2025-01-04T12:27:25.917525", 
      "helpful": 10, 
      "id": "42f9a7a3-ca51-4467-9834-b7b495d46c69", 
      "product_id": "fbdc1a9f-cdf2-4963-bcbb-afbf2bf21316", 
      "rating": 5, 
      "title": "\u00a1Excelente juguete!", 
      "updated_at": "2025-01-04T12:27:25.917527", 
      "user_id": "e380679a-b505-4106-baef-d709016e6f28"
    }
  ]
}
```
### Añadir al Carrito
```bash
curl -X POST "http://mini:<Puerto del kong proxy que apunta al 80>/api/cart/items" \
-H "Content-Type: application/json" \
-H "Authorization: Bearer <Token Jwt>" \
-d '{
  "user_id": "<Id del usuario>",
  "product_id": "<Id del producto>",
  "quantity": 2
}'
```
### Debe devolver un mensaje como 
```json
{
  "message": "Producto a\u00f1adido al carrito exitosamente."
}
```
### Ver Carrito
```bash
curl -X GET "http://mini:<Puerto del kong proxy que apunta al 80>/api/cart?user_id=<Id del usuario>" \
-H "Content-Type: application/json" \
-H "Authorization: Bearer <Token Jwt>"
```
### Debe devolver un mensaje como 
```json
{
  "cart_id": "b74d8548-dd3b-4212-848d-4a9c060bd1ad", 
  "created_at": "2025-01-04T12:54:04.037480", 
  "items": [
    {
      "cart_item_id": "94f3bae2-9beb-4c72-b7c6-3ea55e9236de", 
      "price": 10.99, 
      "product_id": "fbdc1a9f-cdf2-4963-bcbb-afbf2bf21316", 
      "product_images": [
        "https://via.placeholder.com/32", 
        "https://via.placeholder.com/32"
      ], 
      "product_name": "Pelota para perros", 
      "quantity": 2
    }
  ], 
  "total_amount": 21.98, 
  "updated_at": "2025-01-04T12:54:04.039989"
}
```
### Realizar Pedido
```bash
curl -X POST http://mini:<Puerto del kong proxy que apunta al 80>/api/orders \
-H "Content-Type: application/json" \
-H "Authorization: Bearer <Token Jwt>" \
-d '{
  "user_id": "<Id del usuario>",
  "payment_method": "credit_card"
}'
```
### Debe devolver un mensaje como 
```json
{
  "message": "Pedido creado exitosamente.", 
  "order_id": "fa625a48-23fe-4e11-a4b2-49571f6c8dee"
}
```