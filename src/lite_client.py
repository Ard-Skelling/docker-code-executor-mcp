import json
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

# Create server parameters for stdio connection
server_params = StdioServerParameters(
    command="python",  # Executable
    args=["src/mcp_server_simplified.py"],  # Optional command line arguments
    env=None,  # Optional environment variables
)


# Optional: create a sampling callback
async def handle_sampling_message(
    message: types.CreateMessageRequestParams,
) -> types.CreateMessageResult:
    return types.CreateMessageResult(
        role="assistant",
        content=types.TextContent(
            type="text",
            text="Hello, world! from model",
        ),
        model="gpt-3.5-turbo",
        stopReason="endTurn",
    )


async def main():
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(
            read, write, sampling_callback=handle_sampling_message
        ) as session:
            # Initialize the connection
            await session.initialize()

            executor_result = await session.call_tool("create_executor")

            if not executor_result:
                print("Failed to create executor")
                return
        
            executor_id = json.loads(executor_result.content[0].text)["executor_id"]
            print(f"Executor created successfully: {executor_id}")

            # Create project directory
            print("Creating project directory...")
            await session.call_tool("create_directory", {"executor_id": executor_id, "dir_path": "demo_project"})

            python_code = """
import os
import sys

# Print some information
print("Hello from Docker container!")
print(f"Python version: {sys.version}")
print(f"Current directory: {os.getcwd()}")

# Create an output file
with open("output.txt", "w") as f:
    f.write("This file was created by the Python script\\n")
    f.write(f"Python version: {sys.version}\\n")

print("Output file created successfully!")
"""

            print("Writing Python file...")
            await session.call_tool("write_file", {"executor_id": executor_id, "file_path": "demo_project/main.py", "content": python_code})
            
            # Execute bash code
            print("Executing Bash code...")
            result = await session.call_tool("execute_code", {"executor_id": executor_id, "code": "cd /workspace/demo_project && python main.py", "language": "bash"})
    
            print(f"Execution result: {'Success' if json.loads(result.content[0].text)['success'] else 'Failed'}")
            print(f"Output:\n{json.loads(result.content[0].text)['output']}")


            code = '''
import os
import sys

# Print some information
print("Hello from Docker container!")
print(f"Python version: {sys.version}")
print(f"Current directory: {os.getcwd()}")
'''

             # Execute Python code
            print("Executing Python code...")
            result = await session.call_tool("execute_code", {"executor_id": executor_id, "code": code, "language": "python"})
    
            print(f"Execution result: {'Success' if json.loads(result.content[0].text)['success'] else 'Failed'}")
            print(f"Output:\n{json.loads(result.content[0].text)['output']}")


            await session.call_tool("delete_executor", {"executor_id": executor_id}) 


if __name__ == "__main__":
    import asyncio
    asyncio.run(main()) 
