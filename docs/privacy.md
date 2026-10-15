# 隐私、数据与清理

公开仓库只包含通用方法、脚本、占位模板和许可证，没有从个人工作区复制笔记、聊天历史、截图、认证配置、实际密钥、设备指纹或私有 Git 历史。

程序运行后仍会在你自己的机器上产生私有数据：

| 位置 | 内容 |
| --- | --- |
| Mac `~/.ssh/windows_remote*` | 私钥、公钥、主机指纹和 SSH 配置；只把公钥交给 Windows |
| Mac `~/.config/windows-remote/desktop.json` | 自动生成的 MCP 认证 token，文件权限 600；不要分享 |
| Mac `~/.local/state/windows-remote` | SSH 控制套接字 |
| Mac 当前目录 `outputs/windows-desktop` | 截图等结果，可能含屏幕上的私人信息 |
| Windows `ROOT` 指定目录 | MCP 认证配置、日志、租约和进程状态 |
| Windows `%LOCALAPPDATA%\WindowsRemote\Scripts` | 长 PowerShell 脚本暂存，可能包含任务输入 |
| Windows `%LOCALAPPDATA%\WindowsRemote\SSH-Setup` | SSH 安装备份与私下连接报告 |

不要把这些文件加入 Git、Issue 或公开截图。`.gitignore` 只减少误提交机会，不能代替检查。

## 停止与移除

`stop` 停止 MCP 及转发；它不删除已经安装的独立环境、认证文件、日志和按需任务。安装的任务没有自动触发器，保留任务定义本身不会让 MCP 持续运行。

完全移除时：先运行 `stop` 并确认关闭；在 Windows 任务计划程序删除 `WindowsRemote-OnDemand`；按需备份后清理专用控制目录、独立环境和上表中的私有产物。不要删除其他工具共用的 Python 环境，也不要为了移除桌面功能卸载仍在使用的 Tailscale / SSH。

需要更换 MCP 认证 token 时，先停止服务，再移走 Mac 的 `desktop.json`，运行 `setup` 生成并部署新值。已有 token 不要手工改成带引号或控制字符的字符串。不要在共享会话仍运行时重新部署。

## 使用边界

- 面向自己拥有或获准操作的设备。工具可以执行任意授权的 PowerShell；它不是命令沙箱。
- 只通过 SSH 转发访问 Windows 的回环端口，不要把桌面 HTTP 服务暴露到公网。
- 默认用于单控制端、单用户桌面。启动失败的清理可能结束该任务，避免多人或多个控制端共用同一个部署。
- 超时、断线、输入失败不代表远端没有执行。先观察实际状态，再决定是否继续，不自动重放有副作用的动作。
- 下载项目、安装 Skill 或接通 MCP 不等于允许代理任意点击、发送消息或处理所有私人内容；实际操作范围仍由你的具体任务决定。
