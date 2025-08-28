# Streamlit OAuth2 Token Exchange Demo

This is a Dockerized Streamlit application for demonstrating OAuth2 Token Exchange flows. The application is now **config-driven** for maximum flexibility and maintainability.

## 📋 Configuration-Driven Architecture

The application now uses a `config.yaml` file to define:

- **Steps**: Step definitions, titles, descriptions, and manual flags
- **Dependencies**: Which steps depend on which other steps
- **CURL Templates**: Dynamic curl command templates with endpoint placeholders
- **Substitution Rules**: How to replace placeholders with actual values from previous steps
- **Execution Order**: The sequence in which steps should be executed
- **Endpoint Defaults**: Fallback endpoints when discovery doesn't provide them

## 🔧 Configuration File Structure

```yaml
steps:
  - id: "a"
    title: "Backend Client Registration"
    description: "Register the backend client with OAuth2 server"
    manual: false

dependencies:
  a: []  # No dependencies
  b: ["a"]  # Depends on step 'a'
  g: ["a", "d", "f"]  # Can depend on multiple steps

curl_templates:
  a: |
    curl -X POST {registration_endpoint}
      -H "Content-Type: application/json"
      -d {{
        "redirect_uris": [],
        "grant_types": ["client_credentials", "refresh_token"]
      }}

substitution_rules:
  b:
    data:
      "<backend-client-id>": "step.a.client_id"
  c:
    auth:
      "<frontend-client-id>": "step.b.client_id"
      "<frontend-client-secret>": "step.b.client_secret"
```

## 🚀 Quick Start

## Quick Start

### Using Docker Compose (Recommended)

1. **Build and run the application:**
   ```bash
   docker-compose up --build
   ```

2. **Run in background:**
   ```bash
   docker-compose up -d --build
   ```

3. **Stop the application:**
   ```bash
   docker-compose down
   ```

3. **View logs:**
   ```bash
   docker-compose logs -f
   ```

## 🎛️ Customizing the Workflow

### Adding New Steps

1. **Add step definition to `config.yaml`:**
```yaml
steps:
  - id: "k"
    title: "Custom Step"
    description: "Your custom OAuth2 step"
    manual: false
```

2. **Define dependencies:**
```yaml
dependencies:
  k: ["j"]  # Depends on step 'j'
```

3. **Add curl template:**
```yaml
curl_templates:
  k: |
    curl -X POST {token_endpoint}
      -H "Content-Type: application/json"
      -d {{"custom": "data"}}
```

4. **Add substitution rules:**
```yaml
substitution_rules:
  k:
    data:
      "<custom-token>": "step.j.access_token"
```

### Modifying Existing Steps

- Edit the corresponding sections in `config.yaml`
- The application will automatically pick up changes on restart
- No code changes required!

## 🔍 Debugging

- **Config Loading**: Check console logs for configuration parsing errors
- **Step Dependencies**: Use the debug panel to see step status
- **CURL Generation**: Monitor logs for endpoint resolution
- **Substitution**: Check logs for value replacement operations

### Using Docker directly

1. **Build the image:**
   ```bash
   docker build -t streamlit-oauth-demo .
   ```

2. **Run the container:**
   ```bash
   docker run -p 8501:8501 -v $(pwd):/app streamlit-oauth-demo
   ```

## Access the Application

Once running, access the application at: http://localhost:8501

## Development

The docker-compose.yml mounts the current directory, so you can make changes to `streamlit_app.py` and see them reflected immediately (Streamlit has hot reload).

## Configuration

- **Port:** 8501 (configurable in docker-compose.yml)
- **Logs:** Stored in `./logs/` directory
- **Health Check:** Available at `/healthz` endpoint

## Troubleshooting

1. **Port already in use:**
   ```bash
   # Change the port mapping in docker-compose.yml
   ports:
     - "8502:8501"  # Use port 8502 instead
   ```

2. **Permission issues:**
   ```bash
   # Ensure logs directory exists and has proper permissions
   mkdir -p logs
   chmod 755 logs
   ```

3. **Container won't start:**
   ```bash
   # Check logs
   docker-compose logs streamlit-app

   # Rebuild without cache
   docker-compose build --no-cache
   ```
