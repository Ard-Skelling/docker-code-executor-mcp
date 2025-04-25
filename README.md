# Docker Code Executor MCP Service

This is an MCP (Model Context Protocol) based Docker code execution service that allows secure code execution in isolated Docker containers. The service can be used to test and execute code snippets or projects in various programming languages in an isolated environment.

## Features

- Secure code execution in isolated Docker containers
- Support for multiple programming languages (Python, Bash, etc.)
- File operation functionality (read, write, list)
- Project structure exploration
- Container lifecycle management
- Support for stdio and SSE transport methods

## Requirements

- Python 3.8+
- Docker
- MCP library v1.6.0+
- docker-py

## Installation

```bash
# Install dependencies using uv
uv pip install mcp==1.6.0 docker

# Or install from pyproject.toml
uv pip install -e .

# Clone repository (if applicable)
git clone https://github.com/yourusername/docker-code-executor.git
cd docker-code-executor
```

## Usage

### Starting the Server

The server can be started with two transport methods:

#### 1. Standard Input/Output (stdio) Mode

```bash
python src/code_executor_mcp_server.py  # Original version (requires specific MCP library components)
# Or use the simplified version
python src/mcp_server_simplified.py     # Simplified version (compatible with current MCP library version)
```

#### 2. HTTP Mode

```bash
export MCP_HTTP_MODE=true
export MCP_HOST=localhost
export MCP_PORT=8000
python src/mcp_server_simplified.py
```

### Using the Client

Connect to the server using an MCP client and execute code:

```bash
# Use the simplified client
python src/mcp_client_simplified.py

# Use HTTP mode
MCP_HTTP_MODE=true MCP_HOST=localhost MCP_PORT=8000 python src/mcp_client_simplified.py
```

Or use the MCP library API for programming:

```python
from mcp.client import ClientSession

# Connect to HTTP server
async with http_client.connect("http://localhost:8000") as session:
    # Initialize session
    await session.initialize({})
    
    # Create executor
    result = await session.call_tool("create_executor", {"docker_image": "python:3-slim"})
    executor_id = result["executor_id"]
    
    # Execute Python code
    code = """
    print("Hello from Docker container!")
    """
    result = await session.call_tool("execute_code", {
        "executor_id": executor_id,
        "language": "python",
        "code": code
    })
    
    print(result)
    
    # Clean up executor
    await session.call_tool("delete_executor", {"executor_id": executor_id})
```

## Implementation Versions

This project provides two implementation versions:

1. **Complete Version** (`code_executor_mcp_server.py` and `code_executor_mcp_client.py`):
   - Uses the complete MCP server components
   - Supports stdio and SSE transport modes
   - Requires specific versions of the MCP library

2. **Simplified Version** (`mcp_server_simplified.py` and `mcp_client_simplified.py`):
   - Compatible with the MCP library in the current environment
   - Uses FastMCP and basic functions of the MCP server
   - Supports stdio and HTTP transport modes
   - Provides the same API and feature set as the complete version

## API Functions

The server provides the following tools:

- `create_executor` - Create a new Docker code executor
- `execute_code` - Execute code in the container
- `delete_executor` - Delete executor and clean up resources
- `list_directory` - List directory contents
- `read_file` - Read file contents
- `write_file` - Write content to a file
- `create_directory` - Create a new directory
- `project_structure` - Get project structure
- `check_executor_health` - Check executor health status

## Security Considerations

- The service uses network-isolated Docker containers to enhance security
- Additional access restrictions are recommended in production environments
- Input validation is implemented to prevent code injection attacks
- Container resource usage is limited to prevent DoS attacks

## Contributing

Contributions through Issues and Pull Requests are welcome. Please ensure you follow the project's code style and commit message conventions.

## License

This project is licensed under the MIT License. See the LICENSE file for details.
