import asyncio
from typing import Optional
from contextlib import AsyncExitStack
import json
# 导入 MCP 相关模块
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
# 导入 OpenAI API 和环境变量加载工具
from openai import AsyncOpenAI
from dotenv import load_dotenv
# 加载 .env 文件中的环境变量
load_dotenv()  # load environment variables from .env
# 系统提示词，用于定义 AI 助手的行为和能力
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
        # 创建异步上下文管理器，用于动态管理退出回调堆栈
        self.exit_stack = AsyncExitStack()
        # 初始化 OpenAI 客户端
        self.openai = AsyncOpenAI(base_url="https://api.deepseek.com")
        # 存储对话历史
        self.messages = []
        # 存储可用工具
        self.tools = []
        self.tools_updated = False  # 标记工具是否更新
        self._notification_task = None

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
        print(f"Connecting to server with command: {server_params}")
        # 使用 AsyncExitStack 管理 stdio_client 的生命周期
        # stdio的客户端传输：这将通过产生一个进程并通过stdin/stdout来连接到服务器并与它通信。
        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        print("使用 AsyncExitStack 管理 stdio_client 的生命周期")
        print("建立与MCP服务器的连接...，并使用stdio读写流与MCP服务器通信")
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))
        print("初始化MCP客户端会话...")
        await self.session.initialize()
        print("MCP客户端会话初始化完成")

        # 启动通知监听
        self._notification_task = asyncio.create_task(self._handle_notifications())
        print("启动监听任务-mcp-client监听mcp-server的通知")

        # List available tools
        response = await self.session.list_tools()
        self.tools = response.tools
        print(f"获取到MCP服务器可用工具: {[tool.name for tool in self.tools]}")
        
        # Initialize system message with available tools
        tools_desc = "\n- ".join([f"{tool.name}: {tool.description}" for tool in self.tools])
        self.messages = [{
            "role": "system",
            "content": SYSTEM_PROMPT.format(tools=tools_desc)
        }]
        
        print(f"将可用工具填入SYSTEM_PROMPT并初始化系统消息: {self.messages}")

    async def _handle_notifications(self):
        """监听服务器消息和通知"""
        try:
            # 使用 incoming_messages 而不是 notifications
            async for message in self.session.incoming_messages:
                # 处理异常
                if isinstance(message, Exception):
                    print(f"收到错误消息: {message}")
                    continue
                
                # 处理服务器通知
                if isinstance(message, types.ServerNotification):
                    # 获取通知的根对象
                    notification = message.root
                    
                    # 处理工具列表更新通知
                    if isinstance(notification, types.ToolListChangedNotification):
                        print("收到工具列表更新通知")
                        # 重新获取工具列表
                        response = await self.session.list_tools()
                        self.tools = response.tools
                        self.tools_updated = True
                        print(f"MCP Server 的工具列表已更新: {[tool.name for tool in self.tools]}")
                    
                    # 处理资源更新通知
                    elif isinstance(notification, types.ResourceUpdatedNotification):
                        print(f"收到资源更新通知: {notification.params.uri}")
                        # 这里可以添加资源更新的处理逻辑
                    
                    # 处理资源列表变更通知
                    elif isinstance(notification, types.ResourceListChangedNotification):
                        print("收到资源列表变更通知")
                        # 这里可以添加资源列表更新的处理逻辑
                    
                    # 处理提示列表变更通知
                    elif isinstance(notification, types.PromptListChangedNotification):
                        print("收到提示列表变更通知")
                        # 这里可以添加提示列表更新的处理逻辑
                    
                    # 处理进度通知
                    elif isinstance(notification, types.ProgressNotification):
                        print(f"收到进度通知: {notification.params.progressToken} - {notification.params.progress}/{notification.params.total}")
                        # 这里可以添加进度更新的处理逻辑
                    
                    # 处理取消通知
                    elif isinstance(notification, types.CancelledNotification):
                        print(f"收到取消通知: 请求ID {notification.params.requestId}")
                        # 这里可以添加请求取消的处理逻辑
                    
                    # 处理日志消息通知
                    elif isinstance(notification, types.LoggingMessageNotification):
                        print(f"收到日志消息: [{notification.params.level}] {notification.params.message}")
                        # 这里可以添加日志处理的逻辑
                    
                    # 处理其他类型的通知
                    else:
                        print(f"收到未知类型的通知: {notification}")
                
                # 处理服务器请求
                elif hasattr(message, 'request') and hasattr(message, 'respond'):
                    # 这是一个请求响应器 (RequestResponder)
                    request = message.request.root
                    print(f"收到服务器请求: {request}")
                    
                    # 处理创建消息请求
                    if isinstance(request, types.CreateMessageRequest):
                        print("收到创建消息请求")
                        # 这里可以添加处理创建消息请求的逻辑
                    
                    # 处理列出根目录请求
                    elif isinstance(request, types.ListRootsRequest):
                        print("收到列出根目录请求")
                        # 这里可以添加处理列出根目录请求的逻辑
                    
                    # 处理 Ping 请求
                    elif isinstance(request, types.PingRequest):
                        print("收到 Ping 请求")
                        # 这里可以添加处理 Ping 请求的逻辑
                    
                    # 处理其他类型的请求
                    else:
                        print(f"收到未知类型的请求: {request}")
                
                # 处理其他类型的消息
                else:
                    print(f"收到未知类型的消息: {message}")
        except asyncio.CancelledError:
            print("mcp-client对MCP服务器的消息监听已停止")
        except Exception as e:
            print(f"mcp-client对MCP服务器的消息监听出错: {e}")

    async def process_query(self, query: str) -> str:
        """Process a query using OpenAI and available tools"""
        # 在新对话开始时检查是否需要更新系统提示词
        if self.tools_updated:
            print("需要对系统提示词进行更新")
            tools_desc = "\n- ".join([f"{tool.name}: {tool.description}" for tool in self.tools])
            self.messages[0] = {
                "role": "system",
                "content": SYSTEM_PROMPT.format(tools=tools_desc)
            }
            self.tools_updated = False
            print("系统提示词已更新，包含新的工具列表")

        # Add user query to messages
        print(f"收到用户查询: {query}")

        self.messages.append({
            "role": "user",
            "content": query
        })

        print(f"将用户查询添加到对话历史: {self.messages}")

        # Prepare tools for OpenAI
        available_tools = [{
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.inputSchema
            }
        } for tool in self.tools]

        print(f"按照OPENAI API的格式准备工具列表: {[tool['function']['name'] for tool in available_tools]}")

        try:
            # Initial OpenAI API call
            print(f"发送请求到 OpenAI API...")
            response = await self.openai.chat.completions.create(
                model="deepseek-chat",
                messages=self.messages,
                tools=available_tools,
                tool_choice="auto"
            )
            print(f"收到 OpenAI API 响应")
            message = response.choices[0].message
            # Add assistant's response to history (only content and tool_calls)
            print(f"AI 响应内容: {message.content}")
            assistant_message = {
                "role": "assistant",
                "content": message.content or ""
            }
            print(f"将助手的响应添加到对话历史: {assistant_message}")
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
                print(f"将工具调用添加到对话历史: {assistant_message}")
            self.messages.append(assistant_message)
            print(f"将助手的响应添加到对话历史: {self.messages}")
            # If no tool calls, return the response directly
            if not message.tool_calls:
                print(f"没有工具调用，直接返回响应: {message.content}")
                return message.content or ""

            final_text = [message.content] if message.content else []
            print(f"最终响应内容: {final_text}")
            # Handle tool calls
            for tool_call in message.tool_calls:
                try:
                    print('处理工具调用')
                    tool_name = tool_call.function.name
                    tool_args = json.loads(tool_call.function.arguments)
                    print(f"工具名称：{tool_name} , 工具参数：{tool_args}")
                    # Execute tool call
                    result = await self.session.call_tool(tool_name, tool_args)
                    print(f"工具调用结果: {result.content}")
                    # Add tool result to conversation
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_name,
                        "content": str(result.content)  # Ensure content is string
                    })
                    print(f"将工具调用结果添加到对话历史: {self.messages}")
                    final_text.append(f"\n[Tool {tool_name} result: {result.content}]\n")
                except Exception as e:
                    error_msg = f"Error executing tool {tool_name}: {str(e)}"
                    final_text.append(f"\n[Error: {error_msg}]\n")
                    continue

            # Get final response from OpenAI
            print(f"发送请求到 OpenAI API...")
            response = await self.openai.chat.completions.create(
                model="deepseek-chat",
                messages=self.messages
            )
            print(f"收到 OpenAI API 响应")
            final_message = response.choices[0].message
            self.messages.append({
                "role": "assistant",
                "content": final_message.content or ""
            })
            print(f"将助手的响应添加到对话历史: {self.messages}")
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
                    print("用户请求退出")
                    break
                    
                response = await self.process_query(query)
                print("最终响应:\n" + response)
                    
            except Exception as e:
                print(f"\nError: {str(e)}")
    
    async def cleanup(self):
        """Clean up resources"""
        print("清理资源")
        if self._notification_task:
            self._notification_task.cancel()
            try:
                await self._notification_task
            except asyncio.CancelledError:
                pass
        await self.exit_stack.aclose()
        print("资源清理完成")
async def main():
    print("交互式聊天程序启动")
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