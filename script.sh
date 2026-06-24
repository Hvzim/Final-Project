
DEPLOYMENT="deployment.yaml"
SERVICE="service.yaml"

# Verifica se o minikube está instalado e rodando
if command -v minikube >/dev/null 2>&1; then
  echo "Verificando se o minikube está rodando..."
  if ! minikube status | grep -q "Running"; then
    echo "Minikube não está rodando. Iniciando minikube..."
    minikube start
  else
    echo "Minikube já está rodando."
  fi
else
  echo "Minikube não instalado, certifique-se de ter um cluster Kubernetes local ativo."
fi

echo "Aplicando o deployment..."
kubectl apply -f $DEPLOYMENT

echo "Aplicando o service..."
kubectl apply -f $SERVICE

echo "Aguarde os pods iniciarem..."
kubectl wait --for=condition=available --timeout=60s deployment/livros-api

echo "Iniciando port-forward para localhost:8000 -> service porta 80..."

# Rodar o port-forward em background
kubectl port-forward svc/livros-api-service 8000:80 >/dev/null 2>&1 &

# Dá um tempinho para garantir que o port-forward iniciou
sleep 3

# Detecta sistema operacional para abrir navegador
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
  xdg-open http://localhost:8000
elif [[ "$OSTYPE" == "darwin"* ]]; then
  open http://localhost:8000
elif [[ "$OSTYPE" == "cygwin" ]] || [[ "$OSTYPE" == "msys" ]]; then
  start http://localhost:8000
else
  echo "Abra seu navegador em: http://localhost:8000"
fi

echo "Aplicação disponível em http://localhost:8000"
echo "Use Ctrl+C para parar o port-forward quando quiser."
# Mantém o script rodando para não matar o port-forward
wait