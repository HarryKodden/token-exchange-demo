# Token Exchange Demo Helm Chart

This Helm chart deploys the RFC8693 Token Exchange Demo application, a Streamlit-based interactive demonstration of OAuth2 Token Exchange flows.

## Prerequisites

- Kubernetes 1.19+
- Helm 3.0+

## Installing the Chart

To install the chart with the release name `token-exchange-demo`:

```bash
helm install token-exchange-demo ./helm/token-exchange-demo
```

## Configuration

The following table lists the configurable parameters of the token-exchange-demo chart and their default values.

| Parameter | Description | Default |
|-----------|-------------|---------|
| `replicaCount` | Number of replicas | `1` |
| `image.repository` | Image repository | `token-exchange-demo` |
| `image.tag` | Image tag | `""` (uses Chart AppVersion) |
| `image.pullPolicy` | Image pull policy | `IfNotPresent` |
| `service.type` | Service type | `ClusterIP` |
| `service.port` | Service port | `8501` |
| `service.targetPort` | Target port | `8501` |
| `ingress.enabled` | Enable ingress | `false` |
| `ingress.hosts[0].host` | Ingress host | `token-exchange-demo.local` |
| `ingress.hosts[0].paths[0].path` | Ingress path | `/` |
| `ingress.hosts[0].paths[0].pathType` | Ingress path type | `Prefix` |
| `resources.limits.cpu` | CPU limit | `500m` |
| `resources.limits.memory` | Memory limit | `512Mi` |
| `resources.requests.cpu` | CPU request | `100m` |
| `resources.requests.memory` | Memory request | `128Mi` |
| `env` | Environment variables | See values.yaml |
| `config.enabled` | Enable config ConfigMap | `true` |
| `healthCheck.enabled` | Enable health checks | `true` |

## Building and Pushing the Docker Image

Before deploying, you need to build and push the Docker image:

```bash
# Build the image
docker build -t token-exchange-demo:latest .

# Tag for your registry
docker tag token-exchange-demo:latest your-registry/token-exchange-demo:latest

# Push to registry
docker push your-registry/token-exchange-demo:latest
```

Then update `values.yaml` with your image repository:

```yaml
image:
  repository: your-registry/token-exchange-demo
  tag: latest
```

## Accessing the Application

### Using Port Forwarding

```bash
kubectl port-forward svc/token-exchange-demo 8501:8501
```

Then access the application at `http://localhost:8501`

### Using Ingress

Enable ingress in `values.yaml`:

```yaml
ingress:
  enabled: true
  hosts:
    - host: your-domain.com
```

## Health Checks

The application includes health checks that verify the Streamlit service is responding. The health endpoint is `/?healthz=true`.

## Configuration

The application configuration is stored in a ConfigMap and mounted at `/app/config.yaml`. The configuration defines the OAuth2 flow steps and their dependencies.

## Uninstalling the Chart

To uninstall the chart:

```bash
helm uninstall token-exchange-demo
```

## Development

For development, you can mount the source code as a volume by modifying the deployment template or using development overrides.

## License

This Helm chart is licensed under the MIT License - see the [LICENSE](../LICENSE) file for details.