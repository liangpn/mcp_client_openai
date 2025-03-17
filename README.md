# 适配 OpenAI SDK 构建 MCP Client

## 官方文档
- [开发 MCP Client](https://modelcontextprotocol.io/quickstart/client)
- [MCP Client Python 示例代码](https://github.com/modelcontextprotocol/quickstart-resources/tree/main/mcp-client-python)

---

## 项目背景
开发这个适配 OpenAI SDK 的 MCP Client 的原因是，在按照官方示例构建 MCP Client 时，我发现官方示例代码中没有适配 OpenAI SDK 的代码。

---

## 文件说明
- **`client.py`**：适配了 OpenAI SDK 的 MCP Client。
- **`client_new.py`**：为解决我在Windows遇到的问题而适配的版本。
- **`client_20250316.py`**：增加了日志以及增加接收来自server的一些特定消息。请看我的知乎文章-[从MCP Client-Server 生命周期出发，深入研究 MCP 的完整交互链路](https://zhuanlan.zhihu.com/p/30515707345) ，里面详细介绍了这个MCP Client的Server生命周期。
- **`weather_new.py`**：增加了模拟动态更新server工具的代码。与`client_20250316.py`一起使用。
---

## 遇到的问题
在构建过程中，我遇到了一些问题。具体可以阅读下我的知乎文章[如何构建自己的MCP Client]([https://www.zhihu.com/column/c_1883808228573418480](https://zhuanlan.zhihu.com/p/29695874893))，也可以持续关注我的[MCP专栏](https://www.zhihu.com/column/c_1883808228573418480)

![问题截图](https://github.com/user-attachments/assets/f7f89944-fcea-4260-869b-0e3621f396af)

---

## 最后
希望这个项目能对大家有所帮助。


### 问题反馈
如果您在使用过程中遇到任何问题，欢迎随时反馈。

---

### 项目贡献
如果您对这个项目感兴趣，欢迎提交 Pull Request 或 Issue，共同完善这个适配 OpenAI SDK 的 MCP Client。

