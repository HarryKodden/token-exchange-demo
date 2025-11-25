import streamlit as st
import json
import requests
import logging
from typing import Dict, Any, Optional
from urllib.parse import urljoin
import yaml
import os
import urllib.parse

if os.getenv("LOGLEVEL", "info").lower() == "debug":
    logging.getLogger().setLevel(logging.DEBUG)
    logging.debug("📝 Debug logging enabled")
    
# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # Console output
        logging.FileHandler('debug.log')  # File output
    ]
)
logger = logging.getLogger(__name__)


# Load configuration
def load_config() -> Dict[str, Any]:
    """Load configuration from config.yaml file"""
    config_path = os.path.join(os.path.dirname(__file__), 'config.yaml')
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        logger.info("✅ Configuration loaded successfully")
        return config
    except FileNotFoundError:
        logger.error(f"❌ Configuration file not found: {config_path}")
        st.error(f"Configuration file not found: {config_path}")
        return {}
    except yaml.YAMLError as e:
        logger.error(f"❌ Error parsing configuration: {e}")
        st.error(f"Error parsing configuration: {e}")
        return {}

# Load configuration at module level
CONFIG = load_config()


def get_step_info(step_id: str) -> Dict[str, Any]:
    """Get step information from config"""
    steps = CONFIG.get('steps', [])
    step_info = next((s for s in steps if s['id'] == step_id), None)
    if step_info:
        return step_info
    else:
        # Fallback for missing steps
        return {
            'id': step_id,
            'title': f'Step {step_id}',
            'description': f'Step {step_id} description',
            'manual': False
        }

# Page configuration
st.set_page_config(
    page_title="RFC8693 Token Exchange Demo",
    page_icon="🚀",
    layout="wide"
)

# Health check endpoint - simple approach for Docker health checks
query_params = st.query_params
if "healthz" in query_params:
    # Return a simple health response
    st.markdown("OK")
    st.markdown("Streamlit OAuth2 Demo is running")
    st.stop()

# Initialize session state FIRST
logger.info("🔧 Initializing session state variables")
if 'current_step' not in st.session_state:
    st.session_state.current_step = None
    logger.debug("📝 Initialized current_step")
if 'oauth_server_validated' not in st.session_state:
    st.session_state.oauth_server_validated = False
    logger.debug("📝 Initialized oauth_server_validated")
if 'oauth_server_url' not in st.session_state:
    st.session_state.oauth_server_url = ""
    logger.debug("📝 Initialized oauth_server_url")
if 'oauth_endpoints' not in st.session_state:
    st.session_state.oauth_endpoints = {}
    logger.debug("📝 Initialized oauth_endpoints")
if 'discovery_response' not in st.session_state:
    st.session_state.discovery_response = None
    logger.debug("📝 Initialized discovery_response")
if 'step_status' not in st.session_state:
    # Initialize step status based on config
    step_status = {}
    steps = CONFIG.get('steps', [])
    execution_order = CONFIG.get('execution_order', [])

    for step in execution_order:
        if step == execution_order[0]:  # First step is always candidate
            step_status[step] = 'candidate'
        else:
            step_status[step] = 'not_candidate'

    st.session_state.step_status = step_status
    logger.debug("📝 Initialized step_status from config")
if 'step_responses' not in st.session_state:
    st.session_state.step_responses = {}
    logger.debug("📝 Initialized step_responses")
if 'step_execution_order' not in st.session_state:
    st.session_state.step_execution_order = CONFIG.get('execution_order', [])
    logger.debug("📝 Initialized step_execution_order from config")

# Initialize session state for CURL commands
if 'curl_commands_initialized' not in st.session_state:
    st.session_state.curl_commands_initialized = False
    logger.debug("📝 Initialized curl_commands_initialized")
if 'curl_commands' not in st.session_state:
    st.session_state.curl_commands = {}
    logger.debug("📝 Initialized curl_commands")
if 'debug_test_curl' not in st.session_state:
    st.session_state.debug_test_curl = False
    logger.debug("📝 Initialized debug_test_curl")
if 'debug_test_json' not in st.session_state:
    st.session_state.debug_test_json = False
    logger.debug("📝 Initialized debug_test_json")
if 'show_response_modal' not in st.session_state:
    st.session_state.show_response_modal = None
    logger.debug("📝 Initialized show_response_modal")
if 'api_key' not in st.session_state:
    st.session_state.api_key = ""
    logger.debug("📝 Initialized api_key")

logger.info("✅ Session state initialization completed")

# Title
st.title("🚀 RFC8693 Token Exchange Flow")
st.markdown("*Interactive demonstration of OAuth2 Token Exchange steps*")

# Add debug logging
logger.info("🚀 Streamlit app started")
logger.debug(f"Session state keys: {list(st.session_state.keys())}")

# Initialize session state for CURL commands
if 'curl_commands_initialized' not in st.session_state:
    st.session_state.curl_commands_initialized = False
if 'curl_commands' not in st.session_state:
    st.session_state.curl_commands = {}

def validate_oauth_server(server_url: str) -> tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Validate OAuth2 server by checking well-known discovery endpoint.
    Returns: (success, message, endpoints_dict)
    """
    logger.info(f"🔍 Validating OAuth2 server: {server_url}")

    if not server_url or not server_url.startswith(('http://', 'https://')):
        logger.warning("❌ Invalid server URL provided")
        return False, "Please enter a valid HTTPS URL", None

    try:
        # Construct well-known discovery URL
        discovery_url = urljoin(server_url.rstrip('/') + '/', '.well-known/openid-configuration')
        # discovery_url = urljoin(server_url.rstrip('/') + '/', '.well-known/oauth-authorization-server')

        logger.debug(f"📡 Discovery URL: {discovery_url}")

        # Make request with timeout
        response = requests.get(discovery_url, timeout=10)
        response.raise_for_status()

        discovery_data = response.json()
        logger.info(f"✅ Discovery endpoint responded with {len(discovery_data)} fields")

        # Validate required endpoints exist
        required_endpoints = ['issuer', 'registration_endpoint', 'authorization_endpoint', 'token_endpoint']
        missing_endpoints = [ep for ep in required_endpoints if ep not in discovery_data]

        if missing_endpoints:
            logger.error(f"❌ Missing required endpoints: {missing_endpoints}")
            return False, f"Missing required endpoints: {', '.join(missing_endpoints)}", None

        # Extract relevant endpoints
        endpoints = {
            'issuer': discovery_data.get('issuer'),
            'authorization_endpoint': discovery_data.get('authorization_endpoint'),
            'token_endpoint': discovery_data.get('token_endpoint'),
            'userinfo_endpoint': discovery_data.get('userinfo_endpoint'),
            'introspection_endpoint': discovery_data.get('introspection_endpoint'),
            'registration_endpoint': discovery_data.get('registration_endpoint'),
            'end_session_endpoint': discovery_data.get('end_session_endpoint'),
            'jwks_uri': discovery_data.get('jwks_uri'),
            'device_authorization_endpoint': discovery_data.get('device_authorization_endpoint'),  # OAuth 2.0 Device Auth Grant
            'scopes_supported': discovery_data.get('scopes_supported', []),
            'response_types_supported': discovery_data.get('response_types_supported', []),
            'grant_types_supported': discovery_data.get('grant_types_supported', [])
        }

        logger.info(f"✅ OAuth2 server validation successful for {server_url}")
        logger.debug(f"📋 Discovered endpoints: {endpoints}")
        
        # Log which endpoints are missing and using defaults
        missing_endpoints = []
        for key, value in endpoints.items():
            if value is None and not key.endswith('_supported'):
                missing_endpoints.append(key)
        
        if missing_endpoints:
            logger.warning(f"⚠️ Missing endpoints (will use defaults): {missing_endpoints}")
        else:
            logger.info("✅ All standard endpoints discovered")

        return True, "OAuth2 server validated successfully!", endpoints

    except requests.exceptions.Timeout:
        logger.error("⏰ Connection timeout - server may be unreachable")
        return False, "Connection timeout - server may be unreachable", None
    except requests.exceptions.ConnectionError:
        logger.error("🔌 Connection failed - check the server URL")
        return False, "Connection failed - check the server URL", None
    except requests.exceptions.HTTPError as e:
        logger.error(f"🔴 HTTP error: {e.response.status_code} - {e.response.reason}")
        return False, f"HTTP error: {e.response.status_code} - {e.response.reason}", None
    except json.JSONDecodeError:
        logger.error("📄 Invalid JSON response from discovery endpoint")
        return False, "Invalid JSON response from discovery endpoint", None
    except Exception as e:
        logger.error(f"💥 Unexpected error: {str(e)}")
        return False, f"Unexpected error: {str(e)}", None

def get_step_status(step: str) -> tuple[str, str]:
    """
    Get the status and color for a step based on dependencies.
    Returns: (status, color)
    """
    status = st.session_state.step_status.get(step, 'not_candidate')
    
    if status == 'completed':
        return 'completed', 'green'
    elif status == 'candidate':
        return 'candidate', 'yellow'
    else:
        return 'not_candidate', 'red'

def can_execute_step(step: str) -> bool:
    """Check if a step can be executed based on its dependencies from config"""
    dependencies = CONFIG.get('dependencies', {}).get(step, [])

    # If no dependencies, step can be executed
    if not dependencies:
        return True

    # Check if all dependencies are completed
    for dep in dependencies:
        # Special handling for manual steps - if it's a manual step and completed, it counts
        if dep in st.session_state.step_status:
            dep_status = st.session_state.step_status[dep]
            if dep_status != 'completed':
                # Check if it's a manual step that might be bypassed
                steps_config = CONFIG.get('steps', [])
                dep_config = next((s for s in steps_config if s['id'] == dep), None)
                if dep_config and dep_config.get('manual', False):
                    # Manual step can be bypassed if other dependencies are met
                    continue
                else:
                    return False
        else:
            return False

    return True

def update_step_status(step: str, success: bool):
    """Update step status and enable next step if successful"""
    old_status = st.session_state.step_status.get(step, 'not_candidate')

    if success:
        st.session_state.step_status[step] = 'completed'
        logger.info(f"✅ Step {step} completed successfully")

        # Enable next step if it exists
        step_index = st.session_state.step_execution_order.index(step)
        if step_index + 1 < len(st.session_state.step_execution_order):
            next_step = st.session_state.step_execution_order[step_index + 1]
            st.session_state.step_status[next_step] = 'candidate'
            logger.info(f"🎯 Step {next_step} is now available")
            
            # Special case: when step 'd' completes, also enable step 'g' 
            # (since 'f' is a manual step)
            if step == 'd' and 'g' in st.session_state.step_status:
                st.session_state.step_status['g'] = 'candidate'
                logger.info(f"🎯 Step g is also now available (since f is manual)")
    else:
        st.session_state.step_status[step] = 'candidate'  # Reset to candidate on failure
        logger.warning(f"⚠️ Step {step} failed, reset to candidate")

    logger.debug(f"📊 Step {step} status changed from {old_status} to {st.session_state.step_status[step]}")

def show_step_response_modal(step: str):
    """Show step response in a modal popup using Streamlit's dialog component"""

    # Add custom CSS to make the dialog wider for response data
    st.markdown("""
    <style>
    /* Target the dialog container */
    div[data-testid="stDialog"] {
        width: 95vw !important;
        max-width: 1400px !important;
        max-height: 90vh !important;
    }

    /* Target the dialog content area */
    div[data-testid="stDialog"] > div[data-testid="stVerticalBlock"] {
        width: 100% !important;
        max-width: none !important;
    }

    /* Make code blocks wider and more readable */
    div[data-testid="stCodeBlock"] {
        max-width: none !important;
        max-height: 500px !important;
        overflow-y: auto !important;
    }
    </style>
    """, unsafe_allow_html=True)

    @st.dialog(f"📄 Step {step} Response")
    def modal_content():
        if step in st.session_state.step_responses:
            response = st.session_state.step_responses[step]

            # Response content
            st.markdown("**📊 Response Data:**")

            # Format JSON with syntax highlighting
            json_str = json.dumps(response, indent=2, ensure_ascii=False)
            st.code(json_str, language="json")

            # Show HTTP status if available
            if "_http_status" in response:
                status = response["_http_status"]
                status_color = "🟢" if status < 400 else "🔴"
                st.markdown(f"**{status_color} HTTP Status:** {status} {response.get('_http_reason', '')}")

            # Close button
            if st.button("❌ Close", use_container_width=True):
                st.session_state.show_response_modal = None
                st.rerun()
        else:
            st.error(f"No response available for step {step}")
            if st.button("❌ Close", use_container_width=True):
                st.session_state.show_response_modal = None
                st.rerun()

    modal_content()

def show_step_response_tooltip(step: str):
    """Show step response in a tooltip-like display"""
    if step in st.session_state.step_responses:
        response = st.session_state.step_responses[step]
        
        # Create a collapsible section for the response with custom styling
        st.markdown("""
        <style>
        .step-response-expander {
            border: 2px solid #28a745 !important;
            border-radius: 5px !important;
            background: linear-gradient(135deg, #f8fff9 0%, #e8f5e8 100%) !important;
        }
        .step-response-expander summary {
            color: #28a745 !important;
            font-weight: bold !important;
        }
        </style>
        """, unsafe_allow_html=True)
        
        with st.expander(f"📄 Step {step} Response", expanded=False):
            # Format JSON with syntax highlighting
            json_str = json.dumps(response, indent=2, ensure_ascii=False)
            st.code(json_str, language="json")
    else:
        st.info(f"No response available for step {step}")

def create_step_button_with_hover(step: str, title: str, disabled: bool = False) -> bool:
    """Create a step button with a document icon button next to it for showing responses"""
    status, color = get_step_status(step)
    emoji = "🟢" if color == 'green' else "🟡" if color == 'yellow' else "🔴"

    # Create columns for step button and document icon
    col1, col2 = st.columns([4, 1])

    with col1:
        # Create step button
        button_clicked = st.button(
            f"{emoji} {step}) {title}",
            use_container_width=True,
            disabled=disabled,
            key=f"step_{step}_button"
        )

    with col2:
        # Create document icon button for responses (only if step has a response)
        response_button_clicked = False
        if step in st.session_state.step_responses:
            response_button_clicked = st.button(
                "📄",
                key=f"response_{step}_button",
                help=f"View Step {step} Response"
            )
    
    # Special handling for step C - show verification URI if available
    if step == 'c' and color == 'green' and step in st.session_state.step_responses:
        response = st.session_state.step_responses[step]
        if 'verification_uri_complete' in response:
            verification_url = response['verification_uri_complete']
            user_code = response.get('user_code', 'N/A')

            # Ensure verification URLs are full FQDN URLs
            base_url = st.session_state.oauth_server_url.rstrip('/')
            if verification_url.startswith('/'):
                # Relative URL - prepend base URL
                verification_url = base_url + verification_url
                logger.debug(f"🔗 Constructed full verification URL: {verification_url}")

            st.markdown("---")

            # Display clickable verification URL
            st.markdown("**🌐 Click below to complete authentication:**")
            st.markdown(f"**👉 [Complete Device Authorization]({verification_url})**")
            
    
    # Show response when document button is clicked
    if response_button_clicked and step in st.session_state.step_responses:
        st.session_state.show_response_modal = step
        st.rerun()

    return button_clicked

def show_oauth_setup():
    """Show the initial OAuth2 server setup screen"""
    st.title("🔧 OAuth2 Server Configuration")
    st.markdown("*Configure your OAuth2 server to get started*")

    st.markdown("---")

    # Input section
    col1, col2 = st.columns([3, 1])

    with col1:
        server_url = st.text_input(
            "OAuth2 Server URL",
            value=st.session_state.oauth_server_url,
            placeholder="https://your-oauth2-server.com",
            help="Enter the base URL of your OAuth2/OpenID Connect server"
        )

    with col2:
        verify_button = st.button("🔍 Verify Server", type="primary", use_container_width=True)

    # Validation logic
    if verify_button and server_url:
        with st.spinner("Validating OAuth2 server..."):
            success, message, endpoints = validate_oauth_server(server_url)

        if success:
            st.session_state.oauth_server_validated = True
            st.session_state.oauth_server_url = server_url
            st.session_state.oauth_endpoints = endpoints
            st.session_state.discovery_response = endpoints
            # Generate dynamic CURL commands and initialize step responses
            st.session_state.curl_commands = get_dynamic_curl_commands()
            st.session_state.curl_commands_initialized = True
            logger.info("✅ OAuth2 server validation and curl command generation completed")
            st.success(message)
            st.rerun()
        else:
            st.error(message)

    # Show discovery results if validated
    if st.session_state.oauth_server_validated and st.session_state.discovery_response:
        st.markdown("---")
        st.markdown("### 📋 Discovery Results")

        # Show key endpoints
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**🔗 Key Endpoints:**")
            endpoints = st.session_state.discovery_response
            st.write(f"**Issuer:** {endpoints.get('issuer', 'N/A')}")
            st.write(f"**Authorization:** {endpoints.get('authorization_endpoint', 'N/A')}")
            st.write(f"**Token:** {endpoints.get('token_endpoint', 'N/A')}")
            st.write(f"**UserInfo:** {endpoints.get('userinfo_endpoint', 'N/A')}")

        with col2:
            st.markdown("**⚙️ Server Capabilities:**")
            st.write(f"**Scopes:** {', '.join(endpoints.get('scopes_supported', ['N/A'])[:3])}...")
            st.write(f"**Response Types:** {', '.join(endpoints.get('response_types_supported', ['N/A']))}")
            st.write(f"**Grant Types:** {', '.join(endpoints.get('grant_types_supported', ['N/A']))}")

        # Continue button
        if st.button("🚀 Continue to Token Exchange Demo", type="primary", use_container_width=True):
            st.rerun()

    # Reset button
    if st.session_state.oauth_server_validated:
        st.markdown("---")
        if st.button("🔄 Configure Different Server", use_container_width=True):
            st.session_state.oauth_server_validated = False
            st.session_state.oauth_server_url = ""
            st.session_state.oauth_endpoints = {}
            st.session_state.discovery_response = None
            st.rerun()

def execute_step_request(step: str) -> tuple[bool, Dict[str, Any]]:
    """
    Execute the actual HTTP request for a given step.
    Returns: (success, response_data)
    """
    logger.info(f"🚀 Executing step {step}")

    if step not in st.session_state.curl_commands:
        logger.error(f"❌ No command found for step {step}")
        return False, {"error": f"No command found for step {step}"}

    try:
        # Get the curl command
        curl_cmd = st.session_state.curl_commands[step]
        logger.debug(f"📡 Executing command for step {step}")
        logger.debug(f"📝 Raw curl command (repr): {repr(curl_cmd)}")
        logger.debug(f"📝 Raw curl command (first 200 chars): {curl_cmd[:200]}")

        # Parse the curl command and convert to requests call
        success, response_data = parse_and_execute_curl(curl_cmd, step)

        if success:
            logger.info(f"✅ Step {step} executed successfully")
        else:
            logger.warning(f"⚠️ Step {step} execution failed: {response_data.get('error', 'Unknown error')}")

        return success, response_data

    except Exception as e:
        logger.error(f"💥 Execution failed for step {step}: {str(e)}")
        return False, {"error": f"Execution failed: {str(e)}"}

def parse_and_execute_curl(curl_cmd: str, step: str) -> tuple[bool, Dict[str, Any]]:
    """
    Parse curl command and execute as HTTP request.
    Returns: (success, response_data)
    """
    logger.debug(f"🔧 Parsing curl command for step {step}")

    try:
        # Extract method, URL, headers, and data from curl command
        # Handle different line break formats
        if '\\n' in curl_cmd:
            lines = curl_cmd.strip().split('\\n')
        elif '\n' in curl_cmd:
            lines = curl_cmd.strip().split('\n')
        else:
            # Single line command
            lines = [curl_cmd.strip()]

        logger.debug(f"📋 Split into {len(lines)} lines: {lines}")

        method = "GET"
        url = ""
        headers = {}
        data = None
        auth = None
        data_lines = []  # Collect multi-line data
        in_data_section = False

        for line in lines:
            line = line.strip()
            if line.startswith('curl -X'):
                # Extract method and URL from the same line
                parts = line.split()
                if len(parts) >= 3:
                    method = parts[2]
                    # The URL should be the next part after the method
                    if len(parts) > 3:
                        url = parts[3].strip('"')
                    logger.debug(f"📝 Method: {method}")
                    logger.debug(f"🎯 URL from curl line: {url}")
            elif line.startswith('-H'):
                # Extract header
                header_line = line[3:].strip('"')
                if ':' in header_line:
                    key, value = header_line.split(':', 1)
                    headers[key.strip()] = value.strip()
                    logger.debug(f"📋 Header: {key.strip()} = {value.strip()}")
            elif line.startswith('-d'):
                # Start collecting data (might span multiple lines)
                data_str = line[3:].strip('"')
                data_lines.append(data_str)
                in_data_section = True
                logger.debug(f"📄 Starting data collection: {repr(data_str)}")
                logger.debug(f"📄 Data line starts with: {repr(data_str[:20])}")
            elif in_data_section and line and not line.startswith('curl') and not line.startswith('-'):
                # Continue collecting multi-line data
                data_lines.append(line)
                logger.debug(f"📄 Continuing data collection: {repr(line)}")
            elif line.startswith('-u'):
                # Extract basic auth
                auth_str = line[3:].strip('"')
                if ':' in auth_str:
                    username, password = auth_str.split(':', 1)
                    auth = (username, password)
                    logger.debug(f"🔐 Basic auth configured for user: {username}")
            elif not line.startswith('curl') and 'http' in line and not url:
                # Extract URL from standalone lines (fallback)
                url = line.strip('"')
                logger.debug(f"🎯 URL from standalone line: {url}")

        # Process collected data
        if data_lines:
            logger.debug(f"📄 Data lines before joining: {data_lines}")
            
            # Check if this is JSON data (starts with { or [)
            first_line = data_lines[0].strip() if data_lines else ""
            is_json_data = first_line.startswith('{') or first_line.startswith('[')
            
            if is_json_data:
                # For JSON data, join lines as-is without cleaning quotes
                data_str = ''.join(data_lines).strip()
                logger.debug(f"📄 JSON data joined as-is: {repr(data_str)}")
            else:
                # For form data, clean and join properly
                cleaned_data_lines = []
                for line in data_lines:
                    # Remove surrounding quotes and clean the line
                    cleaned_line = line.strip().strip('"').strip("'")
                    if cleaned_line:  # Only add non-empty lines
                        cleaned_data_lines.append(cleaned_line)
                
                # Join with & for form data, or handle as single string for other formats
                if len(cleaned_data_lines) == 1:
                    data_str = cleaned_data_lines[0]
                else:
                    # Check if this looks like form data (contains = signs)
                    if any('=' in line for line in cleaned_data_lines):
                        data_str = '&'.join(cleaned_data_lines)
                    else:
                        data_str = ''.join(cleaned_data_lines)
                
                logger.debug(f"📄 Cleaned data lines: {cleaned_data_lines}")
            
            logger.debug(f"📄 Raw data string: {repr(data_str)}")

            if data_str.startswith('{') or data_str.startswith('"'):
                # JSON data
                try:
                    logger.debug(f"🔍 Attempting JSON parse on: {repr(data_str)}")
                    data = json.loads(data_str)
                except json.JSONDecodeError as e:
                    logger.error(f"❌ JSON parsing failed: {e}")
                    # Try to identify the issue
                    if '\n' in data_str:
                        logger.debug("📄 Data contains newlines - this might cause parsing issues")
                    if '\\' in data_str:
                        logger.debug("📄 Data contains backslashes - this might cause parsing issues")
                    data = data_str
                except Exception as e:
                    logger.error(f"💥 Unexpected error during JSON parsing: {e}")
                    logger.error(f"💥 Error type: {type(e)}")
                    data = data_str
            elif '=' in data_str and '&' in data_str:
                # Form-urlencoded data (key=value pairs separated by &)
                try:
                    from urllib.parse import parse_qs, unquote
                    # Parse the form data
                    parsed_data = parse_qs(data_str, keep_blank_values=True)
                    # Convert to single values (not lists) for simple form data
                    data = {key: unquote(value[0]) if isinstance(value, list) and len(value) == 1 else value 
                           for key, value in parsed_data.items()}
                    logger.debug(f"✅ Form data parsing successful: {data}")
                    logger.info(f"✅ Successfully parsed form data with {len(data)} fields")
                except Exception as e:
                    logger.error(f"❌ Form data parsing failed: {e}")
                    logger.error(f"❌ Failed data: {repr(data_str)}")
                    data = data_str
            elif '=' in data_str:
                # Single key=value pair (form data)
                try:
                    if '&' not in data_str:
                        # Single parameter
                        key, value = data_str.split('=', 1)
                        from urllib.parse import unquote
                        data = {unquote(key): unquote(value)}
                        logger.debug(f"✅ Single form parameter parsing successful: {data}")
                    else:
                        # Multiple parameters
                        from urllib.parse import parse_qs, unquote
                        parsed_data = parse_qs(data_str, keep_blank_values=True)
                        data = {key: unquote(value[0]) if isinstance(value, list) and len(value) == 1 else value 
                               for key, value in parsed_data.items()}
                        logger.debug(f"✅ Multiple form parameters parsing successful: {data}")
                    logger.info(f"✅ Successfully parsed form data")
                except Exception as e:
                    logger.error(f"❌ Form parameter parsing failed: {e}")
                    logger.error(f"❌ Failed data: {repr(data_str)}")
                    data = data_str
            else:
                # Plain string data
                data = data_str
                logger.debug(f"📄 Plain string data: {data}")

        logger.debug(f"🎯 Target URL: {url}")
        logger.debug(f"📋 Headers: {headers}")
        logger.debug(f"📄 Data: {data}")

        # Validate we have a URL
        if not url or not url.startswith(('http://', 'https://')):
            logger.error(f"❌ Invalid or missing URL: '{url}'")
            return False, {"error": f"Invalid or missing URL: '{url}'"}

        # Validate we have required components for POST requests
        if method == "POST" and not data:
            logger.warning("⚠️ POST request without data - this might be intentional")

        # Replace dynamic values from previous step responses
        url, headers, data, auth = substitute_dynamic_values(step, url, headers, data, auth)

        # Execute the request
        logger.info(f"📡 Making {method} request to {url}")

        if method == "POST":
            logger.debug(f"📤 Data type check: {type(data)}, isinstance(data, dict): {isinstance(data, dict)}")
            logger.debug(f"📤 Raw data before sending: {repr(data)}")
            
            # Check Content-Type to determine how to send the data
            content_type = headers.get('Content-Type', '').lower()
            is_form_data = 'application/x-www-form-urlencoded' in content_type or 'multipart/form-data' in content_type
            
            logger.debug(f"📤 Content-Type check: '{content_type}', is_form_data: {is_form_data}")
            
            if isinstance(data, dict):
                if is_form_data or not content_type:
                    # Send as form data
                    logger.debug(f"📤 Sending form data (dict): {data}")
                    logger.debug(f"📤 Headers for form request: {headers}")
                    # Set Content-Type if not already set
                    if not content_type:
                        headers['Content-Type'] = 'application/x-www-form-urlencoded'
                        logger.debug(f"📤 Set Content-Type to: {headers['Content-Type']}")
                    logger.info(f"📝 Sending as form data (dict detected)")

                    payload = urllib.parse.urlencode(data)
                    logger.debug(f"📤 AUTH: {auth}")
                    logger.debug(f"📤 URL-encoded payload: {repr(payload)}")
                    response = requests.post(url, headers=headers, data=payload, auth=auth, timeout=10)
                else:
                    # Send as JSON data
                    logger.debug(f"📤 Sending JSON data: {json.dumps(data, indent=2)}")
                    logger.debug(f"📤 Headers for JSON request: {headers}")
                    logger.debug(f"📤 Content-Type header: {headers.get('Content-Type', 'Not set')}")
                    logger.info(f"✅ Sending as JSON request (dict detected)")
                    response = requests.post(url, headers=headers, json=data, auth=auth, timeout=10)
            else:
                # Handle string data - could be JSON or form data
                is_json_content = 'application/json' in content_type
                
                if is_json_content:
                    # Try to parse as JSON and send as JSON
                    try:
                        json_data = json.loads(data)
                        logger.debug(f"📤 Sending JSON data (string parsed to dict): {json.dumps(json_data, indent=2)}")
                        logger.debug(f"📤 Headers for JSON request: {headers}")
                        logger.info(f"✅ Sending as JSON request (string parsed to JSON)")
                        response = requests.post(url, headers=headers, json=json_data, auth=auth, timeout=10)
                    except json.JSONDecodeError:
                        # If JSON parsing fails, send as raw data
                        logger.debug(f"📤 Sending raw data (JSON parsing failed): {repr(data)}")
                        logger.debug(f"📤 Headers for raw request: {headers}")
                        logger.info(f"📄 Sending as raw data (JSON parsing failed)")
                        response = requests.post(url, headers=headers, data=data, auth=auth, timeout=10)
                else:
                    # Send as form data
                    logger.debug(f"📤 Sending form data: {repr(data)}")
                    logger.debug(f"📤 Headers for form request: {headers}")
                    logger.debug(f"📤 Content-Type header: {headers.get('Content-Type', 'Not set')}")
                    logger.info(f"📝 Sending as form data (string detected)")
                    response = requests.post(url, headers=headers, data=data, auth=auth, timeout=10)
        elif method == "GET":
            response = requests.get(url, headers=headers, auth=auth, timeout=10)
        else:
            logger.error(f"❌ Unsupported HTTP method: {method}")
            return False, {"error": f"Unsupported HTTP method: {method}"}

        # Process response
        logger.info(f"📨 Response status: {response.status_code}")

        try:
            response_data = response.json()
            logger.debug(f"📄 JSON response received")
        except:
            response_data = {"response": response.text}
            logger.debug(f"📄 Text response received: {repr(response.text)}")

        # Add HTTP status info
        response_data["_http_status"] = response.status_code
        response_data["_http_reason"] = response.reason

        # Post-process verification URLs for device authorization responses
        if step == 'c' and response_data.get("_http_status", 0) < 400:
            base_url = st.session_state.oauth_server_url.rstrip('/')
            # Ensure verification URLs are full FQDN URLs
            for url_field in ['verification_uri', 'verification_uri_complete']:
                if url_field in response_data and response_data[url_field]:
                    url = response_data[url_field]
                    if url.startswith('/'):
                        # Relative URL - prepend base URL
                        full_url = base_url + url
                        response_data[url_field] = full_url
                        logger.debug(f"🔗 Constructed full {url_field}: {full_url}")

        success = response.status_code < 400
        logger.info(f"{'✅' if success else '❌'} Request {'successful' if success else 'failed'}")

        return success, response_data

    except Exception as e:
        logger.error(f"💥 Request parsing/execution failed: {str(e)}")
        return False, {"error": f"Request parsing/execution failed: {str(e)}"}

def substitute_dynamic_values(step: str, url: str, headers: Dict, data, auth) -> tuple[str, Dict, Any, Optional[tuple]]:
    """
    Substitute dynamic values from previous step responses into the request using config rules.
    """
    # Get previous step responses for substitution
    prev_responses = st.session_state.step_responses
    substitution_rules = CONFIG.get('substitution_rules', {})

    logger.debug(f"🔄 Substituting dynamic values for step {step}, url: {url}, data: {data}")

    # Helper function to resolve step.field references
    def resolve_step_reference(ref: str) -> str:
        """Resolve a step.field reference to actual value"""
        
        logger.debug(f"🔍 Resolving reference: {ref}")
        if ref == 'api_key':
            return st.session_state.get('api_key', '')
        if '.' in ref:
            step_id, field = ref.split('.', 1)
            if step_id in prev_responses:
                logger.debug(f"🔍 Found previous response for step {step_id} := {prev_responses[step_id]}")
                return prev_responses[step_id].get(field, f'<{ref}>')
            
        logger.error(f"⚠️ Unable to resolve reference: {ref}")
        return f'<{ref}>'

    # Get substitution rules for this step
    step_rules = substitution_rules.get(step, {})

    logger.debug(f"🔄 Substitution rules for step {step}: {step_rules}")
    
    # Apply URL substitutions
    if 'url' in step_rules:
        for placeholder, ref in step_rules['url'].items():
            url = url.replace(placeholder, resolve_step_reference(ref))
            logger.debug(f"� Updated URL: {placeholder} -> {resolve_step_reference(ref)}")

    # Apply header substitutions
    if 'headers' in step_rules:
        for placeholder, ref in step_rules['headers'].items():
            for header_name, header_value in headers.items():
                if placeholder in str(header_value):
                    headers[header_name] = header_value.replace(placeholder, resolve_step_reference(ref))
                    logger.debug(f"🔄 Updated header {header_name}: {placeholder} -> {resolve_step_reference(ref)}")

    # Apply data substitutions
    if 'data' in step_rules:
        logger.debug(f"🔄 Applying data substitutions: {step_rules['data']}")
        for placeholder, ref in step_rules['data'].items():
            logger.debug(f"🔄 Processing data substitution: {placeholder} -> {ref}")
            replacement = resolve_step_reference(ref)
            logger.debug(f"🔄 Resolved {ref} to: {replacement}")
            if isinstance(data, str):
                data = data.replace(placeholder, replacement)
                logger.debug(f"🔄 Updated data string: {placeholder} -> {replacement}")
            elif isinstance(data, dict):
                # Update dictionary values directly (handles nested structures)
                data = substitute_in_dict(data, placeholder, replacement)
            elif isinstance(data, list):
                # Handle list data
                data = [substitute_in_value(item, placeholder, replacement) for item in data]
                logger.debug(f"🔄 Updated data list: {placeholder} -> {replacement}")

    # Apply auth substitutions
    if 'auth' in step_rules:
        if auth and len(auth) == 2:
            username, password = auth
            logger.debug(f"🔄 Auth before substitution: {username}:{password}")
            
            # Substitute placeholders in username and password
            for placeholder, ref in step_rules['auth'].items():
                if placeholder in username:
                    username = username.replace(placeholder, resolve_step_reference(ref))
                    logger.debug(f"🔄 Updated auth username: {placeholder} -> {resolve_step_reference(ref)}")
                if placeholder in password:
                    password = password.replace(placeholder, resolve_step_reference(ref))
                    logger.debug(f"🔄 Updated auth password: {placeholder} -> {resolve_step_reference(ref)}")
            
            auth = (username, password)
            logger.debug(f"🔄 Auth after substitution: {username}:{password}")

    logger.debug(f"🔄 Data after substitution: {data}")

    return url, headers, data, auth

def substitute_in_dict(d: dict, placeholder: str, replacement: str) -> dict:
    """Recursively substitute placeholders in dictionary values"""
    logger.debug(f"🔄 Substituting in dict: {placeholder} -> {replacement}")
    result = {}
    for key, value in d.items():
        logger.debug(f"🔄 Processing dict key {key}: {value}")
        result[key] = substitute_in_value(value, placeholder, replacement)
    return result

def substitute_in_value(value, placeholder: str, replacement: str):
    """Substitute placeholders in any value type"""
    logger.debug(f"🔄 Substituting in value {value} (type: {type(value)}): {placeholder} -> {replacement}")
    if isinstance(value, str):
        if placeholder in value:
            new_value = value.replace(placeholder, replacement)
            logger.debug(f"🔄 String substitution: {value} -> {new_value}")
            return new_value
        else:
            logger.debug(f"🔄 Placeholder {placeholder} not found in string {value}")
            return value
    elif isinstance(value, list):
        logger.debug(f"🔄 Processing list with {len(value)} items")
        return [substitute_in_value(item, placeholder, replacement) for item in value]
    elif isinstance(value, dict):
        return substitute_in_dict(value, placeholder, replacement)
    else:
        return value

def get_dynamic_curl_commands():
    """Generate CURL commands using discovered OAuth2 endpoints and config templates"""
    base_url = st.session_state.oauth_server_url.rstrip('/')
    endpoints = st.session_state.oauth_endpoints
    curl_templates = CONFIG.get('curl_templates', {})
    endpoint_defaults = CONFIG.get('endpoint_defaults', {})

    logger.info(f"🔧 Generating dynamic curl commands from config for {base_url}")
    logger.debug(f"📍 Available endpoints: {list(endpoints.keys())}")

    # Helper function to get endpoint with intelligent defaults
    def get_endpoint_with_default(endpoint_name, default_path):
        """Get endpoint with fallback to config defaults"""
        discovered = endpoints.get(endpoint_name)
        if discovered:
            logger.debug(f"✅ Using discovered {endpoint_name}: {discovered}")
            return discovered
        else:
            # Try config default first, then fallback to provided default
            config_default = endpoint_defaults.get(endpoint_name)
            if config_default:
                default_url = base_url + config_default
                logger.warning(f"⚠️ {endpoint_name} not discovered, using config default: {default_url}")
                return default_url
            else:
                default_url = base_url + default_path
                logger.warning(f"⚠️ {endpoint_name} not discovered, using fallback default: {default_url}")
                return default_url

    commands = {}

    # Generate commands for each step in the config
    for step_id, template in curl_templates.items():
        if template and template.strip():
            # Replace endpoint placeholders in template
            command = template
            command = command.replace('{registration_endpoint}', get_endpoint_with_default('registration_endpoint', '/register'))
            command = command.replace('{device_authorization_endpoint}', get_endpoint_with_default('device_authorization_endpoint', '/device/authorize'))
            command = command.replace('{token_endpoint}', get_endpoint_with_default('token_endpoint', '/token'))
            command = command.replace('{userinfo_endpoint}', get_endpoint_with_default('userinfo_endpoint', '/userinfo'))
            command = command.replace('{introspection_endpoint}', get_endpoint_with_default('introspection_endpoint', '/introspect'))
            command = command.replace('{api_key}', st.session_state.get('api_key', ''))

            commands[step_id] = command

    logger.info(f"✅ Generated {len(commands)} curl commands from config")
    
    # Log endpoint usage summary
    logger.info("📊 Endpoint Usage Summary:")
    endpoint_usage = {}
    for step_id, template in curl_templates.items():
        if template and '{registration_endpoint}' in template:
            endpoint_usage.setdefault('registration_endpoint', []).append(step_id)
        if template and '{device_authorization_endpoint}' in template:
            endpoint_usage.setdefault('device_authorization_endpoint', []).append(step_id)
        if template and '{token_endpoint}' in template:
            endpoint_usage.setdefault('token_endpoint', []).append(step_id)
        if template and '{userinfo_endpoint}' in template:
            endpoint_usage.setdefault('userinfo_endpoint', []).append(step_id)
        if template and '{introspection_endpoint}' in template:
            endpoint_usage.setdefault('introspection_endpoint', []).append(step_id)

    for endpoint_name, steps in endpoint_usage.items():
        discovered = endpoints.get(endpoint_name)
        status = "✅ discovered" if discovered else "⚠️ default"
        steps_str = ', '.join(steps)
        logger.info(f"  {endpoint_name}: {status} (used by steps: {steps_str})")
    
    logger.debug("📋 Generated commands preview:")
    for step, cmd in commands.items():
#       logger.debug(f"  {step}: {cmd.split('\\\\')[0]}...")  # Show first line only
        logger.debug(f"  {step} raw command (repr): {repr(cmd[:100])}...")
        
        # Extract and log the endpoint being used
        first_line = cmd.split('\\')[0].strip()
        if 'curl -X' in first_line:
            # Extract URL from curl command
            parts = first_line.split()
            if len(parts) >= 4:
                url = parts[3]
                logger.debug(f"  {step} endpoint: {url}")
        
        # Also log if the command contains the expected data
        if '-d' in cmd:
            logger.debug(f"  {step} has data: {'{' in cmd and '}' in cmd}")

    return commands

def test_curl_parsing():
    """Test function to debug curl command parsing"""
    test_cmd = '''curl -X POST https://example.com/register \\
  -H "Content-Type: application/json" \\
  -d '{
    "redirect_uris": [],
    "grant_types": [
        "client_credentials",
        "refresh_token",
        "urn:ietf:params:oauth:grant-type:token-exchange"
    ],
    "scope": "openid profile offline_access"
  }'
  '''

    logger.info("🧪 Testing curl command parsing...")
    logger.debug(f"📝 Test command: {repr(test_cmd)}")

    # Test the parsing logic
    success, response_data = parse_and_execute_curl(test_cmd, 'test')
    logger.info(f"🧪 Test result: success={success}, data={response_data}")

def test_json_parsing():
    """Test function to debug JSON parsing specifically"""
    test_json_str = '''{
    "redirect_uris": [],
    "grant_types": [
        "client_credentials",
        "refresh_token",
        "urn:ietf:params:oauth:grant-type:token-exchange"
    ],
    "scope": "openid profile offline_access"
  }'''

    logger.info("🧪 Testing JSON parsing...")
    logger.debug(f"📝 Test JSON string: {repr(test_json_str)}")

    try:
        parsed = json.loads(test_json_str)
        logger.info(f"✅ JSON parsing successful: {type(parsed)}")
        logger.debug(f"📄 Parsed data: {parsed}")
        return True, parsed
    except json.JSONDecodeError as e:
        logger.error(f"❌ JSON parsing failed: {e}")
        logger.error(f"❌ Failed data: {repr(test_json_str)}")
        return False, str(e)
    except Exception as e:
        logger.error(f"💥 Unexpected error: {e}")
        return False, str(e)

# Initialize session state for CURL commands
if 'curl_commands_initialized' not in st.session_state:
    st.session_state.curl_commands_initialized = False
if 'curl_commands' not in st.session_state:
    st.session_state.curl_commands = {}

# Call test function for debugging
if st.session_state.get('debug_test_curl', False):
    test_curl_parsing()
    st.session_state.debug_test_curl = False

# Call JSON parsing test function for debugging
if st.session_state.get('debug_test_json', False):
    test_json_parsing()
    st.session_state.debug_test_json = False

# Regenerate CURL commands if requested
if st.session_state.get('debug_regenerate_commands', False):
    if st.session_state.oauth_server_validated:
        st.session_state.curl_commands = get_dynamic_curl_commands()
        st.session_state.curl_commands_initialized = True
        logger.info("🔧 CURL commands manually regenerated")
    st.session_state.debug_regenerate_commands = False

def show_api_modal(step: str, title: str):
    """Show modal with API details using Streamlit's modal component"""

    # Add custom CSS to make the dialog wider
    st.markdown("""
    <style>
    /* Target the dialog container */
    div[data-testid="stDialog"] {
        width: 95vw !important;
        max-width: 1400px !important;
        max-height: 90vh !important;
    }
    
    /* Target the dialog content area */
    div[data-testid="stDialog"] > div[data-testid="stVerticalBlock"] {
        width: 100% !important;
        max-width: none !important;
    }
    
    /* Make code blocks wider */
    div[data-testid="stCodeBlock"] {
        max-width: none !important;
    }
    
    /* Make columns use full width */
    div[data-testid="stHorizontalBlock"] {
        width: 100% !important;
    }
    </style>
    """, unsafe_allow_html=True)

    @st.dialog(title)
    def modal_content():
        st.markdown("**📡 CURL Command:**")

        # Get the command, with fallback for uninitialized state
        if not st.session_state.curl_commands_initialized or step not in st.session_state.curl_commands:
            command = f"Command for step {step} not available. Please configure OAuth2 server first."
        else:
            command = st.session_state.curl_commands[step]
            logger.debug(f"🎯 Modal showing command for step {step}: {repr(command[:100])}...")
        st.code(command, language="bash")

        col1, col2 = st.columns(2)
        with col1:
            if can_execute_step(step):
                if st.button("▶️ Execute Request", type="primary", use_container_width=True):
                    with st.spinner("Executing request..."):
                        # Execute real HTTP request
                        http_success, response = execute_step_request(step)
                        
                        # Store response
                        st.session_state.step_responses[step] = response
                        
                        # Update step status
                        update_step_status(step, http_success)
                        
                        # Show success message
                        if http_success:
                            st.success(f"✅ Step {step} executed successfully!")
                        else:
                            st.error(f"❌ Step {step} failed!")
                        
                        st.rerun()
            else:
                st.button("▶️ Execute Request", disabled=True, use_container_width=True)

        with col2:
            if st.button("❌ Close", use_container_width=True):
                st.rerun()

    modal_content()

# Main app logic - show setup or demo based on validation status
if not st.session_state.oauth_server_validated:
    show_oauth_setup()
    st.stop()  # Stop execution here to prevent showing main content

# API Key Configuration
st.markdown("### 🔑 API Configuration")
api_key = st.text_input("X-API-KEY (required for client registration)", value=st.session_state.api_key, type='password', help="Enter the API key required for steps A and B")
if api_key != st.session_state.api_key:
    st.session_state.api_key = api_key
    if st.session_state.oauth_server_validated:
        st.session_state.curl_commands = get_dynamic_curl_commands()
        st.session_state.curl_commands_initialized = True
        logger.info("🔧 CURL commands regenerated with new API key")

# Create three columns for the different sections
col1, col2, col3 = st.columns(3)

# Status Summary
with st.expander("📊 Step Status Overview", expanded=False):
    status_summary = []
    for step in st.session_state.step_execution_order:
        status, color = get_step_status(step)
        emoji = "🟢" if color == 'green' else "🟡" if color == 'yellow' else "🔴"
        status_text = "Completed" if status == 'completed' else "Candidate" if status == 'candidate' else "Blocked"
        status_summary.append(f"{emoji} **{step.upper()}**: {status_text}")
    
    st.markdown(" | ".join(status_summary))
    
    # Show discovery results if OAuth2 server is validated
    if st.session_state.oauth_server_validated and st.session_state.discovery_response:
        st.markdown("---")
        st.markdown("### 🔍 OAuth2 Server Discovery Results")
        
        endpoints = st.session_state.discovery_response
        disc_col1, disc_col2 = st.columns(2)
        
        with disc_col1:
            st.markdown("**🔗 Key Endpoints:**")
            st.write(f"**Issuer:** {endpoints.get('issuer', 'N/A')}")
            st.write(f"**Authorization:** {endpoints.get('authorization_endpoint', 'N/A')}")
            st.write(f"**Token:** {endpoints.get('token_endpoint', 'N/A')}")
            st.write(f"**UserInfo:** {endpoints.get('userinfo_endpoint', 'N/A')}")
            
        with disc_col2:
            st.markdown("**⚙️ Server Capabilities:**")
            scopes = endpoints.get('scopes_supported', [])
            st.write(f"**Scopes:** {', '.join(scopes[:3])}{'...' if len(scopes) > 3 else ''}")
            response_types = endpoints.get('response_types_supported', [])
            st.write(f"**Response Types:** {', '.join(response_types)}")
            grant_types = endpoints.get('grant_types_supported', [])
            st.write(f"**Grant Types:** {', '.join(grant_types)}")

# Debug section (collapsible)
with st.expander("🐛 Debug Information", expanded=False):
    st.write("**Session State Status:**")
    debug_col1, debug_col2 = st.columns(2)

    with debug_col1:
        st.write(f"✅ OAuth2 Validated: {st.session_state.oauth_server_validated}")
        st.write(f"🌐 Server URL: {st.session_state.oauth_server_url}")
        st.write(f"📡 Commands Initialized: {st.session_state.get('curl_commands_initialized', False)}")

    with debug_col2:
        st.write(f"📊 Step Responses Count: {len(st.session_state.step_responses)}")
        st.write(f"🎯 Current Step: {st.session_state.current_step}")
        st.write(f"📝 Commands Available: {len(st.session_state.get('curl_commands', {}))}")

    if st.button("🔄 Refresh Debug Info"):
        st.rerun()

    if st.button("🔧 Regenerate CURL Commands"):
        if st.session_state.oauth_server_validated:
            st.session_state.debug_regenerate_commands = True
            st.rerun()
        else:
            st.warning("⚠️ Please validate OAuth2 server first")

    if st.button("🧪 Test CURL Parsing"):
        st.session_state.debug_test_curl = True
        st.rerun()

    if st.button("🧪 Test JSON Parsing"):
        st.session_state.debug_test_json = True
        st.rerun()

# General Setup Steps (Grey)
with col1:
    st.markdown("""
    <div style='background: linear-gradient(135deg, #6c757d 0%, #495057 100%); color: white; padding: 20px; border-radius: 10px; margin-bottom: 20px;'>
        <h3 style='margin: 0; color: white;'>⚙️ General Setup Steps</h3>
    </div>
    """, unsafe_allow_html=True)

    # Step a) Backend Client Registration
    step_a = get_step_info('a')
    if create_step_button_with_hover('a', step_a['title'], not can_execute_step('a')):
        show_api_modal('a', f"Step a) {step_a['title']}")

    # Step b) Frontend Client Registration
    step_b = get_step_info('b')
    if create_step_button_with_hover('b', step_b['title'], not can_execute_step('b')):
        show_api_modal('b', f"Step b) {step_b['title']}")

# Frontend Steps (Green)
with col2:
    st.markdown("""
    <div style='background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white; padding: 20px; border-radius: 10px; margin-bottom: 20px;'>
        <h3 style='margin: 0; color: white;'>🖥️ Frontend Steps</h3>
    </div>
    """, unsafe_allow_html=True)

    # Step c) User Authentication
    step_c = get_step_info('c')
    if create_step_button_with_hover('c', step_c['title'], not can_execute_step('c')):
        show_api_modal('c', f"Step c) {step_c['title']}")

    # Step d) Token Request & Introspection
    step_d = get_step_info('d')
    if create_step_button_with_hover('d', step_d['title'], not can_execute_step('d')):
        show_api_modal('d', f"Step d) {step_d['title']}")

    # Step e) Userinfo Request
    step_e = get_step_info('e')
    if create_step_button_with_hover('e', step_e['title'], not can_execute_step('e')):
        show_api_modal('e', f"Step e) {step_e['title']}")

    # Step f) Refresh Token Handover (special step - no modal)
    step_f = get_step_info('f')
    if st.button(f"f) {step_f['title']}", use_container_width=True):
        st.info("This step involves transferring the refresh token to the backend client")

# Backend Operations (Blue)
with col3:
    st.markdown("""
    <div style='background: linear-gradient(135deg, #007bff 0%, #6610f2 100%); color: white; padding: 20px; border-radius: 10px; margin-bottom: 20px;'>
        <h3 style='margin: 0; color: white;'>⚙️ Backend Operations</h3>
    </div>
    """, unsafe_allow_html=True)

    # Step g) Token Exchange
    step_g = get_step_info('g')
    if create_step_button_with_hover('g', step_g['title'], not can_execute_step('g')):
        show_api_modal('g', f"Step g) {step_g['title']}")

    # Step h) Refresh Token Request
    step_h = get_step_info('h')
    if create_step_button_with_hover('h', step_h['title'], not can_execute_step('h')):
        show_api_modal('h', f"Step h) {step_h['title']}")

    # Step i) Backend Token Introspection
    step_i = get_step_info('i')
    if create_step_button_with_hover('i', step_i['title'], not can_execute_step('i')):
        show_api_modal('i', f"Step i) {step_i['title']}")

    # Step j) Backend Userinfo Request
    step_j = get_step_info('j')
    if create_step_button_with_hover('j', step_j['title'], not can_execute_step('j')):
        show_api_modal('j', f"Step j) {step_j['title']}")

# Show response modal if one is active
if st.session_state.show_response_modal:
    show_step_response_modal(st.session_state.show_response_modal)

# Footer
st.markdown("---")
st.markdown("*For demonstration purposes only, 2025 Harry Kodden - at - surf.nl*")
