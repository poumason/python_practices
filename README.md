# python_practices


# K8S

## Mongo + Express
- Reference [link](https://www.bogotobogo.com/DevOps/Docker/Docker_Kubernetes_MongoDB_MongoExpress.php) to prepare yaml
- follow cmds to setting localhost port with k8s container port
  1. `kubectl get pods` to get mongo express pod name
  1. `kubectl port-forward ${pod name} 8081:8081` to set localhost:8081 with container:8081