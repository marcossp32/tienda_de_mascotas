
# API RESTful para Tienda de Mascotas

Este proyecto contiene las instrucciones necesarias para configurar y desplegar una API RESTful para una tienda de mascotas, utilizando herramientas como Docker, Minikube, Istio y Kong.

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

### Una vez veamos que el pod de postgres esta corriendo
```bash
kubectl apply -f database/create-tables-job.yml
kubectl apply -f database/insert-data.yml
```

```bash
kubectl apply -f logic/cart-service/kube/
kubectl apply -f logic/category-service/kube/
kubectl apply -f logic/order-service/kube/
kubectl apply -f logic/product-service/kube/
kubectl apply -f logic/review-service/kube/
kubectl apply -f logic/search-service/kube/
kubectl apply -f logic/user-service/kube/
```

## Verificar Estado de los Pods y Servicios
```bash
kubectl get pods -n default
kubectl get svc -n default
```

## En caso de que el pod de de create tables este en not ready y no se hayan creado las tablas, borrar y volver a comprobar
```bash
kubectl delete pod -l app=postgres
kubectl delete pod <pod de createtables>
```

## Si se quiere comprobar que las tablas han sido creadas y estan en el servicio de postgres
```bash
kubectl exec -it <pod de postgres> -- bash
psql -U postgres -d petstore

o

kubectl exec -it <pod de postgres> -- psql -U postgres -d petstore

\dt para ver todas las tablas
```

##  Instalación y Configuración de Kong en Kubernetes con Helm
```bash
Para instalar el repo la primera vez

helm repo add kong https://charts.konghq.com && helm repo update

Cada vez que se ha hecho minikube delete y se ha vuelto a empezar

helm install kong kong/kong --set ingressController.installCRDs=false && \
helm upgrade kong kong/kong --set admin.enabled=true --set admin.http.enabled=true

```

##  Comprobar que todo  esta correcto
```bash
 kubectl get pods
 kubectl get svc
```


##  Aplicar el ingress con las rutas para la API Gateway
```bash
kubectl apply -f kong/kong-ingress.yml
```

## Aplicar el host indicado
```bash
minikube ip
sudo nano /etc/hosts
```
Dentro se debe meter la ip de minikube con el nombre mini de esta manera
```bash
192.168.49.2   mini
```

## Para probar el registro

### Comprueba el puerto del kong proxy para realizar  el curl
```bash
 kubectl get svc
```

```bash
curl -X POST http://mini:<Puerto del kong Proxy corrspondiente al 80>/api/users/register -H "Content-Type: application/json" -d '{
  "username": "prueba",
  "password": "12345",
  "email": "prueba@gmail.com",
  "firstName": "pruebaNombre",
  "lastName": "pruebaApellido",
  "phoneNumber": "123456789"
}'
```

### Debe devolver un mensaje como 
```bash
{"message":"Usuario registrado con \u00e9xito","token":"eyJhbGciOiJqUzI1NnR5cCI6IkpXVCJ9.eyJ1ca12UO98snia82TlkMTk2Y2IthLWExMI5Ndj48ak1hwIjoxNzMxNzU4ODEwfQ.4AzOdX7Q75_yZq9HntelIk2pCw_Ks"}
```

## Para probar el inicio de sesión
```bash
curl -X POST http://mini:<Puerto del kong Proxy corrspondiente al 80>/api/users/login -H "Content-Type: application/json" -d '{
  "username": "prueba",
  "password": "12345"
}'
```
### Debe devolver un mensaje como 
```bash
{"message":"Inicio de sesi\u00f3n exitoso","token":"eyJhbGciOiJqUzI1NnR5cCI6IkpXVCJ9.eyJ1ca12UO98snia82TlkMTk2Y2IthLWExMI5Ndj48ak1hwIjoxNzMxNzU4ODEwfQ.4AzOdX7Q75_yZq9HntelIk2pCw_Ks"}
```


<!-- curl -X GET "http://mini:30142/api/search?q=perro" -H "Content-Type: application/json" -->

<!-- curl -X POST http://mini:30142/api/cart/items \
-H "Content-Type: application/json" \
-d '{
  "product_id": "6a8afe13-aa41-4151-8980-d0d5fa765c75",
  "quantity": 2,
  "user_id": "558b573e-26ab-45a7-8555-b248356b0375"
}' -->

<!-- curl -X POST http://mini:30142/api/orders \
-H "Content-Type: application/json" \
-d '{
  "user_id": "558b573e-26ab-45a7-8555-b248356b0375",
  "payment_method": "credit_card"
}' -->