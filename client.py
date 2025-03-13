import asyncio
from typing import Optional
from contextlib import AsyncExitStack
import json

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()  # load environment variables from .env

SYSTEM_PROMPT = """You are a helpful assistant capable of accessing external functions and engaging in casual chat. Use the responses from these function calls to provide accurate and informative answers. The answers should be natural and hide the fact that you are using tools to access real-time information. Guide the user about available tools and their capabilities. Always utilize tools to access real-time information when required. Engage in a friendly manner to enhance the chat experience.

# Tools
{tools}

# Notes 
- Ensure responses are based on the latest information available from function calls.
- Maintain an engaging, supportive, and friendly tone throughout the dialogue.
- Always highlight the potential of available tools to assist users comprehensively."""

class MCPClient:
    def __init__(self):
        # Initialize session and client objects
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.openai = AsyncOpenAI(base_url="https://api.deepseek.com")
        self.messages = []  # Store conversation history
        self.tools = []    # Store available tools

    async def connect_to_server(self, server_script_path: str):
        """Connect to an MCP server
        
        Args:
            server_script_path: Path to the server script (.py or .js)
        """
        is_python = server_script_path.endswith('.py')
        is_js = server_script_path.endswith('.js')
        if not (is_python or is_js):
            raise ValueError("Server script must be a .py or .js file")
            
        command = "python" if is_python else "node"
        server_params = StdioServerParameters(
            command=command,
            args=[server_script_path],
            env=None
        )
        
        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))
        
        await self.session.initialize()
        
        # List available tools
        response = await self.session.list_tools()
        self.tools = response.tools
        
        # Initialize system message with available tools
        tools_desc = "\n- ".join([f"{tool.name}: {tool.description}" for tool in self.tools])
        self.messages = [{
            "role": "system",
            "content": SYSTEM_PROMPT.format(tools=tools_desc)
        }]
        
        print("\nConnected to server with tools:", [tool.name for tool in self.tools])

    async def process_query(self, query: str) -> str:
        """Process a query using OpenAI and available tools"""
        # Add user query to messages
        self.messages.append({
            "role": "user",
            "content": query
        })

        # Prepare tools for OpenAI
        available_tools = [{
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.inputSchema
            }
        } for tool in self.tools]

        try:
            # Initial OpenAI API call
            response = await self.openai.chat.completions.create(
                model="deepseek-chat",
                messages=self.messages,
                tools=available_tools,
                tool_choice="auto"
            )

            message = response.choices[0].message
            # Add assistant's response to history (only content and tool_calls)
            assistant_message = {
                "role": "assistant",
                "content": message.content or ""
            }
            if message.tool_calls:
                assistant_message["tool_calls"] = [
                    {
                        "id": tool_call.id,
                        "type": "function",
                        "function": {
                            "name": tool_call.function.name,
                            "arguments": tool_call.function.arguments
                        }
                    } for tool_call in message.tool_calls
                ]
            self.messages.append(assistant_message)

            # If no tool calls, return the response directly
            if not message.tool_calls:
                return message.content or ""

            final_text = [message.content] if message.content else []

            # Handle tool calls
            for tool_call in message.tool_calls:
                try:
                    tool_name = tool_call.function.name
                    tool_args = json.loads(tool_call.function.arguments)
                    
                    # Execute tool call
                    result = await self.session.call_tool(tool_name, tool_args)
                    
                    # Add tool result to conversation
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_name,
                        "content": str(result.content)  # Ensure content is string
                    })

                    final_text.append(f"\n[Tool {tool_name} result: {result.content}]\n")

                except Exception as e:
                    error_msg = f"Error executing tool {tool_name}: {str(e)}"
                    final_text.append(f"\n[Error: {error_msg}]\n")
                    continue

            # Get final response from OpenAI
            response = await self.openai.chat.completions.create(
                model="deepseek-chat",
                messages=self.messages
            )
            
            final_message = response.choices[0].message
            self.messages.append({
                "role": "assistant",
                "content": final_message.content or ""
            })
            final_text.append(final_message.content)

            return "\n".join(filter(None, final_text))

        except Exception as e:
            print(f"Debug - Messages: {json.dumps(self.messages, ensure_ascii=False, indent=2)}")
            return f"Error processing query: {str(e)}"

    async def chat_loop(self):
        """Run an interactive chat loop"""
        print("\nMCP Client Started!")
        print("Type your queries or 'quit' to exit.")
        
        while True:
            try:
                query = input("\nQuery: ").strip()
                
                if query.lower() == 'quit':
                    break
                    
                response = await self.process_query(query)
                print("\n" + response)
                    
            except Exception as e:
                print(f"\nError: {str(e)}")
    
    async def cleanup(self):
        """Clean up resources"""
        await self.exit_stack.aclose()

async def main():
    if len(sys.argv) < 2:
        print("Usage: python client.py <path_to_server_script>")
        sys.exit(1)
        
    client = MCPClient()
    try:
        await client.connect_to_server(sys.argv[1])
        await client.chat_loop()
    finally:
        await client.cleanup()

if __name__ == "__main__":
    import sys
    asyncio.run(main())