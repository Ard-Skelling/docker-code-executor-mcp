#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MCP-based Docker Code Executor Server

This server uses the FastMCP class from the MCP library to implement a server that can execute code in Docker containers.
It provides a set of tools that allow clients to create Docker containers, execute code, and manage files.
"""

import asyncio
import docker
import logging
import os
import re
import uuid
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Union
import base64

# Import MCP library
from mcp.server.fastmcp import Context, FastMCP

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("mcp_docker_server")

# Utility functions
def sanitize_path(path: str) -> str:
    """
    Sanitize path to prevent path traversal attacks
    
    Args:
        path: The path to sanitize
        
    Returns:
        Sanitized path
    """
    # Remove all "../" patterns, only allow basic alphanumeric characters and some safe symbols
    sanitized = re.sub(r'\.\./', '', path)
    sanitized = re.sub(r'[^\w\d\-_/. ]', '', sanitized)
    # Ensure path doesn't start with "/" (prevent absolute paths)
    while sanitized.startswith('/'):
        sanitized = sanitized[1:]
    return sanitized

class DockerExecutor:
    """Docker Code Executor"""
    
    def __init__(self, docker_image: str = "python:3-slim", timeout: int = 30):
        """
        Initialize Docker code executor
        
        Args:
            docker_image: Docker image to use
            timeout: Code execution timeout in seconds
        """
        self.docker_image = docker_image
        self.timeout = timeout
        self.client = docker.from_env()
        self.container = None
        self.id = str(uuid.uuid4())
        
        # Ensure image exists
        try:
            self.client.images.get(docker_image)
            logger.info(f"Found image {docker_image}")
        except docker.errors.ImageNotFound:
            logger.info(f"Pulling image {docker_image}...")
            self.client.images.pull(docker_image)
    
    async def start(self) -> None:
        """Start Docker container"""
        if self.container is not None:
            return
            
        # Create container
        self.container = self.client.containers.run(
            self.docker_image,
            command="tail -f /dev/null",  # Keep container running
            detach=True,
            remove=True,  # Auto-remove container after stopping
            working_dir="/workspace",  # Working directory
            # Security settings
            cap_drop=["ALL"],  # Remove all Linux capabilities
            security_opt=["no-new-privileges:true"],  # Prevent gaining new privileges
            mem_limit="256m",  # Memory limit
            cpu_count=1,  # CPU limit
        )
        
        # Create working directory
        self.container.exec_run(
            ["mkdir", "-p", "/workspace"],
            user="root"
        )
        
        logger.info(f"Started container {self.container.short_id}")
    
    async def stop(self) -> None:
        """Stop and clean up Docker container"""
        if self.container is not None:
            try:
                self.container.stop(timeout=2)
                logger.info(f"Container {self.container.short_id} has been stopped")
            except Exception as e:
                logger.error(f"Error stopping container: {e}")
            finally:
                self.container = None
    
    async def execute_code(self, code: str, language: str) -> Dict[str, Any]:
        """
        Execute code in Docker container
        
        Args:
            code: Code to execute
            language: Code language (python, bash, etc.)
            
        Returns:
            Dictionary containing execution results
        """
        await self.start()
        
        try:
            if language.lower() == "python":
                cmd = ["python", "-c", code]
            else:
                cmd = ["bash", "-c", code]
            
            # Run command in sync way
            def docker_exec_run():
                return self.container.exec_run(
                    cmd,
                    workdir="/workspace",
                    demux=True,
                    privileged=False,
                    user="root",
                    tty=False,
                    environment={},
                )
            
            # Get current event loop and execute Docker operation in thread pool
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, docker_exec_run),
                timeout=self.timeout
            )
            
            # Process results
            exit_code = result.exit_code
            stdout = result.output[0] or b""
            stderr = result.output[1] or b""
            
            stdout_str = stdout.decode('utf-8', errors='replace')
            stderr_str = stderr.decode('utf-8', errors='replace')
            
            output = stdout_str
            if stderr_str:
                output += "\n--- stderr ---\n" + stderr_str
            
            return {
                "output": output,
                "exit_code": exit_code,
                "success": exit_code == 0
            }
        except asyncio.TimeoutError:
            logger.error(f"Code execution timed out after {self.timeout} seconds")
            return {
                "output": f"Execution timed out after {self.timeout} seconds",
                "exit_code": 124,  # Standard timeout exit code
                "success": False
            }
        except Exception as e:
            logger.error(f"Error executing code: {e}")
            return {
                "output": f"Execution error: {str(e)}",
                "exit_code": 1,
                "success": False
            }
    
    async def write_file(self, file_path: str, content: str) -> Dict[str, Any]:
        """
        Write file in container's working directory
        
        Args:
            file_path: File path relative to working directory
            content: File content
            
        Returns:
            Dictionary containing operation result
        """
        await self.start()
        
        # Sanitize file path
        safe_path = sanitize_path(file_path)
        
        try:
            # Ensure directory exists
            dir_path = os.path.dirname(f"/workspace/{safe_path}")
            if dir_path != "/workspace":
                mkdir_result = self.container.exec_run(
                    ["bash", "-c", f"mkdir -p {dir_path}"],
                    user="root"
                )
                if mkdir_result.exit_code != 0:
                    return {
                        "success": False,
                        "message": f"Error creating directory: {mkdir_result.output.decode('utf-8', errors='replace')}"
                    }
            
            # Use echo command to create file in container
            # Base64 encode the content to handle special characters and multiline text
            encoded_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
            
            # Use base64 to decode and write to file
            write_cmd = f"echo '{encoded_content}' | base64 -d > /workspace/{safe_path} && chmod 666 /workspace/{safe_path}"
            result = self.container.exec_run(
                ["bash", "-c", write_cmd],
                user="root"
            )
            
            if result.exit_code != 0:
                return {
                    "success": False,
                    "message": f"Error writing file: {result.output.decode('utf-8', errors='replace')}"
                }
            
            return {
                "success": True,
                "message": f"File {file_path} created in container"
            }
        except Exception as e:
            logger.error(f"Error writing file: {e}")
            return {
                "success": False,
                "message": f"Error writing file: {str(e)}"
            }
    
    async def read_file(self, file_path: str) -> Dict[str, Any]:
        """
        Read file from container's working directory
        
        Args:
            file_path: File path relative to working directory
            
        Returns:
            Dictionary containing file content
        """
        await self.start()
        
        # Sanitize file path
        safe_path = sanitize_path(file_path)
        
        try:
            # Check if file exists
            check_result = self.container.exec_run(
                ["bash", "-c", f"[ -f /workspace/{safe_path} ] && echo 'exists' || echo 'not_exists'"],
                user="root"
            )
            
            if check_result.output.decode('utf-8', errors='replace').strip() != 'exists':
                return {
                    "success": False,
                    "message": f"File {file_path} does not exist in container"
                }
            
            # Read file content
            result = self.container.exec_run(
                ["cat", f"/workspace/{safe_path}"],
                user="root"
            )
            
            if result.exit_code != 0:
                return {
                    "success": False,
                    "message": f"Error reading file: {result.output.decode('utf-8', errors='replace')}"
                }
            
            content = result.output.decode('utf-8', errors='replace')
            
            return {
                "success": True,
                "content": content
            }
        except Exception as e:
            logger.error(f"Error reading file: {e}")
            return {
                "success": False,
                "message": f"Error reading file: {str(e)}"
            }
    
    async def list_directory(self, path: str = ".") -> Dict[str, Any]:
        """
        List files and subdirectories in container's working directory
        
        Args:
            path: Path relative to working directory
            
        Returns:
            Dictionary containing directory contents
        """
        await self.start()
        
        # Sanitize path
        safe_path = sanitize_path(path)
        
        try:
            # List directory contents
            result = self.container.exec_run(
                ["ls", "-la", f"/workspace/{safe_path}"],
                workdir="/workspace",
                user="root"
            )
            
            if result.exit_code != 0:
                return {
                    "success": False,
                    "message": f"Directory {path} does not exist or cannot be accessed"
                }
            
            output = result.output.decode('utf-8', errors='replace')
            
            return {
                "success": True,
                "output": output
            }
        except Exception as e:
            logger.error(f"Error listing directory: {e}")
            return {
                "success": False,
                "message": f"Error listing directory: {str(e)}"
            }
    
    async def create_directory(self, dir_path: str) -> Dict[str, Any]:
        """
        Create directory in container's working directory
        
        Args:
            dir_path: Directory path relative to working directory
            
        Returns:
            Dictionary containing operation result
        """
        await self.start()
        
        # Sanitize directory path
        safe_path = sanitize_path(dir_path)
        
        try:
            result = self.container.exec_run(
                ["bash", "-c", f"mkdir -p /workspace/{safe_path} && chmod -R 777 /workspace/{safe_path}"],
                workdir="/workspace",
                user="root"
            )
            
            if result.exit_code != 0:
                return {
                    "success": False,
                    "message": f"Error creating directory: {result.output.decode('utf-8', errors='replace')}"
                }
            
            return {
                "success": True,
                "message": f"Directory {dir_path} created in container"
            }
        except Exception as e:
            logger.error(f"Error creating directory: {e}")
            return {
                "success": False,
                "message": f"Error creating directory: {str(e)}"
            }
    
    async def project_structure(self, path: str = ".") -> Dict[str, Any]:
        """
        Get project structure
        
        Args:
            path: Path relative to working directory
            
        Returns:
            Dictionary containing project structure
        """
        await self.start()
        
        # Sanitize path
        safe_path = sanitize_path(path)
        
        try:
            # Check if directory exists
            check_result = self.container.exec_run(
                ["bash", "-c", f"[ -d /workspace/{safe_path} ] && echo 'exists' || echo 'not_exists'"],
                user="root"
            )
            
            if check_result.output.decode('utf-8', errors='replace').strip() != 'exists':
                return {
                    "success": False,
                    "message": f"Directory {path} does not exist in container"
                }
            
            # First try using tree command
            tree_result = self.container.exec_run(
                ["which", "tree"],
                workdir="/workspace",
                user="root"
            )
            
            if tree_result.exit_code == 0:
                # Tree command exists in container, use it directly
                result = self.container.exec_run(
                    ["tree", f"/workspace/{safe_path}"],
                    workdir="/workspace",
                    user="root"
                )
                tree_output = result.output.decode('utf-8', errors='replace')
                
                return {
                    "success": True,
                    "tree": tree_output,
                    "files": []  # Keep for compatibility
                }
            else:
                # Recursively get file list using find command
                find_result = self.container.exec_run(
                    ["find", f"/workspace/{safe_path}", "-type", "f", "-o", "-type", "d"],
                    workdir="/workspace",
                    user="root"
                )
                
                output = find_result.output.decode('utf-8', errors='replace')
                file_paths = [line.replace("/workspace/", "", 1) for line in output.splitlines() if line.strip()]
                
                # Get file type information
                ls_result = self.container.exec_run(
                    ["find", f"/workspace/{safe_path}", "-type", "d", "-o", "-type", "f", "-printf", "%y %P\n"],
                    workdir="/workspace",
                    user="root"
                )
                
                ls_output = ls_result.output.decode('utf-8', errors='replace')
                file_types = {}
                
                for line in ls_output.splitlines():
                    if not line.strip():
                        continue
                    
                    file_type, file_path = line.split(" ", 1)
                    if file_path.startswith(f"{safe_path}/"):
                        file_path = file_path[len(f"{safe_path}/"):]
                    elif file_path == safe_path:
                        file_path = ""
                    
                    file_types[file_path] = "d" if file_type == "d" else "f"
                
                # Build tree structure
                tree_structure = generate_tree_structure(file_paths, file_types)
                
                # Convert tree structure to string representation
                tree_lines = []
                build_tree_output(tree_structure, tree_lines)
                tree_output = "\n".join(tree_lines)
                
                if not tree_output:
                    tree_output = f"{path}\n└── (empty directory)"
                
                return {
                    "success": True,
                    "tree": tree_output,
                    "files": file_paths  # Keep original output for compatibility
                }
        except Exception as e:
            logger.error(f"Error getting project structure: {e}")
            return {
                "success": False,
                "message": f"Error getting project structure: {str(e)}"
            }

class ExecutorManager:
    """Executor Manager"""
    
    def __init__(self):
        """Initialize executor manager"""
        self.executors: Dict[str, DockerExecutor] = {}
    
    def get_executor(self, executor_id: str) -> Optional[DockerExecutor]:
        """Get executor"""
        return self.executors.get(executor_id)
    
    async def create_executor(self, docker_image: str = "python:3-slim", timeout: int = 30) -> DockerExecutor:
        """Create new executor"""
        executor = DockerExecutor(docker_image, timeout)
        self.executors[executor.id] = executor
        await executor.start()
        return executor
    
    async def delete_executor(self, executor_id: str) -> bool:
        """Delete executor"""
        executor = self.get_executor(executor_id)
        if executor is None:
            return False
            
        await executor.stop()
        del self.executors[executor_id]
        return True
    
    async def cleanup(self) -> None:
        """Clean up all executors"""
        logger.info(f"Cleaning up {len(self.executors)} executors")
        
        for executor_id, executor in list(self.executors.items()):
            try:
                await executor.stop()
                logger.info(f"Executor {executor_id} has been stopped")
            except Exception as e:
                logger.error(f"Error cleaning up executor {executor_id}: {e}")
        
        self.executors.clear()

@dataclass
class AppContext:
    """Application context, manages shared resources"""
    manager: ExecutorManager

@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """
    Manage application lifecycle
    
    Args:
        server: FastMCP server instance
        
    Yields:
        Application context
    """
    # Initialize resources
    manager = ExecutorManager()
    logger.info("Initializing executor manager")
    
    try:
        yield AppContext(manager=manager)
    finally:
        # Clean up resources
        logger.info("Server is shutting down, cleaning up all executors")
        await manager.cleanup()

# Create FastMCP server
app = FastMCP(
    "Docker Code Executor",
    description="Safely execute code in Docker containers",
    lifespan=lifespan
)

# Register tools
@app.tool()
async def create_executor(
    docker_image: str = "python:3-slim",
    timeout: int = 30,
    ctx: Context = None
) -> Dict[str, str]:
    """
    Create a Docker code executor
    
    Args:
        docker_image: Docker image to use
        timeout: Execution timeout in seconds
        ctx: MCP context
        
    Returns:
        Dictionary containing executor_id
    """
    manager = ctx.request_context.lifespan_context.manager
    executor = await manager.create_executor(docker_image, timeout)
    return {
        "executor_id": executor.id,
        "message": f"Executor created using image {docker_image}"
    }

@app.tool()
async def delete_executor(
    executor_id: str,
    ctx: Context = None
) -> Dict[str, Any]:
    """
    Delete Docker executor
    
    Args:
        executor_id: Executor ID
        ctx: MCP context
        
    Returns:
        Operation result
    """
    manager = ctx.request_context.lifespan_context.manager
    success = await manager.delete_executor(executor_id)
    return {
        "success": success,
        "message": "Executor deleted" if success else "Executor not found"
    }

@app.tool()
async def execute_code(
    executor_id: str,
    code: str,
    language: str = "python",
    ctx: Context = None
) -> Dict[str, Any]:
    """
    Execute code in Docker container
    
    Args:
        executor_id: Executor ID
        code: Code to execute
        language: Code language (python, bash, etc.)
        ctx: MCP context
        
    Returns:
        Execution result
    """
    manager = ctx.request_context.lifespan_context.manager
    executor = manager.get_executor(executor_id)
    
    if executor is None:
        return {
            "success": False,
            "message": "Executor not found"
        }
    
    # Log message
    ctx.info(f"Executing {language} code in executor {executor_id}")
    
    return await executor.execute_code(code, language)

@app.tool()
async def write_file(
    executor_id: str,
    file_path: str,
    content: str,
    ctx: Context = None
) -> Dict[str, Any]:
    """
    Write file in Docker container
    
    Args:
        executor_id: Executor ID
        file_path: File path
        content: File content
        ctx: MCP context
        
    Returns:
        Operation result
    """
    manager = ctx.request_context.lifespan_context.manager
    executor = manager.get_executor(executor_id)
    
    if executor is None:
        return {
            "success": False,
            "message": "Executor not found"
        }
    
    return await executor.write_file(file_path, content)

@app.tool()
async def read_file(
    executor_id: str,
    file_path: str,
    ctx: Context = None
) -> Dict[str, Any]:
    """
    Read file from Docker container
    
    Args:
        executor_id: Executor ID
        file_path: File path
        ctx: MCP context
        
    Returns:
        File content
    """
    manager = ctx.request_context.lifespan_context.manager
    executor = manager.get_executor(executor_id)
    
    if executor is None:
        return {
            "success": False,
            "message": "Executor not found"
        }
    
    return await executor.read_file(file_path)

@app.tool()
async def list_directory(
    executor_id: str,
    path: str = ".",
    ctx: Context = None
) -> Dict[str, Any]:
    """
    List directory contents in Docker container
    
    Args:
        executor_id: Executor ID
        path: Directory path
        ctx: MCP context
        
    Returns:
        Directory contents
    """
    manager = ctx.request_context.lifespan_context.manager
    executor = manager.get_executor(executor_id)
    
    if executor is None:
        return {
            "success": False,
            "message": "Executor not found"
        }
    
    return await executor.list_directory(path)

@app.tool()
async def create_directory(
    executor_id: str,
    dir_path: str,
    ctx: Context = None
) -> Dict[str, Any]:
    """
    Create directory in Docker container
    
    Args:
        executor_id: Executor ID
        dir_path: Directory path
        ctx: MCP context
        
    Returns:
        Operation result
    """
    manager = ctx.request_context.lifespan_context.manager
    executor = manager.get_executor(executor_id)
    
    if executor is None:
        return {
            "success": False,
            "message": "Executor not found"
        }
    
    return await executor.create_directory(dir_path)

@app.tool()
async def project_structure(
    executor_id: str,
    path: str = ".",
    ctx: Context = None
) -> Dict[str, Any]:
    """
    Get project structure in Docker container, displayed as a tree
    
    Args:
        executor_id: Executor ID
        path: Directory path
        ctx: MCP context
        
    Returns:
        Project structure tree
    """
    manager = ctx.request_context.lifespan_context.manager
    executor = manager.get_executor(executor_id)
    
    if executor is None:
        return {
            "success": False,
            "message": "Executor not found"
        }
    
    return await executor.project_structure(path)

# Add a simple system status resource
@app.resource("system://status")
def get_system_status() -> str:
    """Get system status information"""
    return "Docker Code Executor server is running normally. Use tools to create executors and run code."

# Add helper functions for generating tree structures
def generate_tree_structure(file_paths, file_types):
    """
    Generate tree structure from file path list
    
    Args:
        file_paths: List of file paths
        file_types: Dictionary of file types
        
    Returns:
        Tree structure dictionary
    """
    root = {"name": "", "type": "d", "children": {}}
    
    for path in sorted(file_paths):
        if not path:  # Root directory
            continue
            
        parts = path.split("/")
        current = root
        
        # Build tree structure
        for i, part in enumerate(parts):
            if i == len(parts) - 1:
                # Leaf node (file or directory)
                file_type = file_types.get(path, "f")
                current["children"][part] = {"name": part, "type": file_type, "children": {}}
            else:
                # Intermediate directory
                if part not in current["children"]:
                    current["children"][part] = {"name": part, "type": "d", "children": {}}
                current = current["children"][part]
    
    return root

def build_tree_output(node, lines, prefix="", is_last=True, is_root=True):
    """
    Build tree output
    
    Args:
        node: Current node
        lines: Output lines list
        prefix: Current line prefix
        is_last: Whether this is the last child of its parent
        is_root: Whether this is the root node
    """
    if not is_root:
        connector = "└── " if is_last else "├── "
        lines.append(f"{prefix}{connector}{node['name']}{'' if node['type'] == 'f' else '/'}")
        
        # Next level prefix
        prefix = prefix + ("    " if is_last else "│   ")
    else:
        # Root node
        if "name" in node and node["name"]:
            lines.append(node["name"] + "/")
            prefix = ""
    
    # Process child nodes
    children = list(node["children"].values())
    for i, child in enumerate(children):
        build_tree_output(child, lines, prefix, i == len(children) - 1, False)

# Main entry point
if __name__ == "__main__":
    # Use MCP library's run method to start the server
    logger.info("Starting Docker Code Executor MCP server...")
    
    if os.environ.get("MCP_SSE_MODE", "false").lower() == "true":
        app.run(transport="sse")
    else:
        logger.info("Running server in stdio mode")
        app.run(transport="stdio") 