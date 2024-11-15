
# API RESTful para Tienda de Mascotas

Este proyecto contiene las instrucciones necesarias para configurar y desplegar una API RESTful para una tienda de mascotas, utilizando herramientas como Docker, Minikube, Istio y Kong.

## Documentación Adicional
- [Documentación API RESTful para Tienda de Mascotas (PDF)](file:///C:/Users/marco/Desktop/UNI/A%C3%91O%204/INTEGRACION%20DE%20APLICACIONES/Practica2/Documentaci%C3%B3n%20API%20RESTful%20para%20Tienda%20de%20Mascotas.pdf)
- [Proyecto Final Integración de Aplicaciones (PDF)](file:///C:/Users/marco/Desktop/UNI/A%C3%91O%204/INTEGRACION%20DE%20APLICACIONES/final_project/PROYECTO%20FINAL%20INTEGRACI%C3%B3N%20DE%20APLICACIONES.pdf)
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

<!-- ## Instalar istio (De momento no)
```bash
curl -L https://istio.io/downloadIstio | sh -
cd istio-1.x.x
export PATH=$PWD/bin:$PATH
istioctl install --set profile=demo -y
kubectl -n istio-system get deploy
``` -->

<!-- ## Habilitar inyección automática de sidecar
```bash
kubectl label namespace default istio-injection=enabled
``` -->

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

## Aplicar Configuraciones en Kubernetes
```bash
kubectl apply -f logic/cart-service/kube/
kubectl apply -f logic/category-service/kube/
kubectl apply -f logic/order-service/kube/
kubectl apply -f logic/product-service/kube/
kubectl apply -f logic/review-service/kube/
kubectl apply -f logic/search-service/kube/
kubectl apply -f logic/user-service/kube/
kubectl apply -f database/deployment.yml
kubectl apply -f database/service.yml
kubectl apply -f database/create-tables-job.yml
```

## Verificar Estado de los Pods y Servicios
```bash
kubectl get pods -n default
kubectl get svc -n default
```

## En caso de que este en not ready el pod de create tables y no se hayan creado las tablas, borrar 
```bash
kubectl delete pod -l app=postgres
kubectl delete pod <pod de createtables>
```

## Si se quiere comprobar que las tablas han sido creadas y estan en el servicio de postgres
```bash
kubectl exec -it <pod de postgres> -- bash
psql -U postgres -d petstore
\dt para ver todas las tablas
```

##  Instalación y Configuración de Kong en Kubernetes con Helm
```bash
helm repo add kong https://charts.konghq.com && helm repo update
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

# Para probar el registro
```bash
 curl -X POST http://mini:30409/api/users/register -H "Content-Type: application/json" -d '{
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

# Para probar el inicio de sesión
```bash
curl -X POST http://mini:30409/api/users/login -H "Content-Type: application/json" -d '{
  "username": "prueba",
  "password": "12345"
}'
```
### Debe devolver un mensaje como 
```bash
{"message":"Inicio de sesi\u00f3n exitoso","token":"eyJhbGciOiJqUzI1NnR5cCI6IkpXVCJ9.eyJ1ca12UO98snia82TlkMTk2Y2IthLWExMI5Ndj48ak1hwIjoxNzMxNzU4ODEwfQ.4AzOdX7Q75_yZq9HntelIk2pCw_Ks"}
```
