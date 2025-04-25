# Docker Code Executor

A secure MCP (Model Context Protocol) based service for executing code in isolated Docker containers. This service provides a safe environment for testing and running code snippets or projects in various programming languages.

## Features

- **Isolated Execution**: Run code securely in Docker containers
- **Multi-language Support**: Execute Python, Bash, and other language code
- **File Operations**: Read, write, and manage files within containers
- **Directory Management**: Create and explore project structures
- **Container Lifecycle**: Full management of execution environments
- **Flexible Transport**: Support for stdio and HTTP communication

## Requirements

- Python 3.8+
- Docker
- MCP library v1.6.0+
- docker-py

## Installation

```bash
# Install dependencies using uv (recommended)
uv pip install mcp==1.6.0 docker

# Or install from pyproject.toml
uv pip install -e .

# Clone the repository (if applicable)
git clone https://github.com/yourusername/docker-code-executor.git
cd docker-code-executor
```

## Usage

### Starting the Server

#### Standard Input/Output (stdio) Mode

```bash
python src/server.py
```


#### SSE Mode

```bash
export MCP_SSE_MODE=true
python src/server.py
```

### Using the Client

The project includes a lite client for interacting with the server:

```bash
# Use the lite client (stdio mode)
python src/lite_client.py
```

## API Reference

The Docker Code Executor provides these core tools:

| Tool | Description |
|------|-------------|
| `create_executor` | Create a new Docker code executor instance |
| `execute_code` | Run code in a container with specified language |
| `delete_executor` | Remove an executor and clean up resources |
| `list_directory` | List contents of a directory in the container |
| `read_file` | Read the contents of a file |
| `write_file` | Write content to a file |
| `create_directory` | Create a new directory |
| `project_structure` | Generate a tree view of the project structure |

## Example Usage

### Client Code Example

```python
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Set up connection to the server
server_params = StdioServerParameters(
    command="python",
    args=["src/server.py"],
    env=None,
)

async def main():
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize the connection
            await session.initialize()

            # Create a Docker executor
            executor_result = await session.call_tool("create_executor")
            executor_id = json.loads(executor_result.content[0].text)["executor_id"]
            
            # Create a project directory
            await session.call_tool("create_directory", {
                "executor_id": executor_id, 
                "dir_path": "my_project"
            })

            # Write a Python file
            python_code = """
import os
print("Hello from Docker container!")
print(f"Current directory: {os.getcwd()}")
"""
            await session.call_tool("write_file", {
                "executor_id": executor_id, 
                "file_path": "my_project/main.py", 
                "content": python_code
            })
            
            # Execute the code
            result = await session.call_tool("execute_code", {
                "executor_id": executor_id, 
                "code": "cd /workspace/my_project && python main.py", 
                "language": "bash"
            })
            
            print(f"Execution result: {json.loads(result.content[0].text)['output']}")
            
            # Clean up resources
            await session.call_tool("delete_executor", {"executor_id": executor_id})

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

## Security Considerations

The Docker Code Executor implements several security measures:

- Isolated Docker containers with resource limits
- Network isolation to prevent unauthorized access
- Input validation to guard against code injection attacks
- Container privilege restrictions
- Resource quotas (memory, CPU) to prevent DoS attacks

For production deployments, consider adding:
- Authentication and authorization
- Rate limiting
- Network firewall rules
- Additional Docker security profiles

## Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

Please ensure your code follows the project's style guidelines and includes appropriate tests.

## License

This project is licensed under the MIT License. See the LICENSE file for details.
