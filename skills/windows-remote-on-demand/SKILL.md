---
name: windows-remote-on-demand
description: 从 macOS 经已配置的 Tailscale/OpenSSH 执行 Windows PowerShell、传文件和使用现有环境；需要查看窗口、点击或输入时按需启用 Windows-MCP，完成后关闭。
---

# 按需操作 Windows

以本 Skill 的实际目录为根。命令和文件调用 `scripts/windows_remote.py`；只有桌面任务才读取 [桌面入口](references/desktop.md)。安装与 SSH 信任应已配置，详情由项目安装说明负责，不在每次调用前重复部署或全套体检。

```bash
python3 <skill-root>/scripts/windows_remote.py info
python3 <skill-root>/scripts/windows_remote.py run --command 'Get-ChildItem -LiteralPath D:\RemoteWork'
python3 <skill-root>/scripts/windows_remote.py run --file <local-script.ps1>
python3 <skill-root>/scripts/windows_remote.py put <local-file> D:/RemoteWork/task/input.bin
python3 <skill-root>/scripts/windows_remote.py get D:/RemoteWork/task/result.bin <local-output>
```

上传前建立目标父目录。两端目录独立，按任务传输；调用已有 Python / CUDA 项目前核对解释器和目录，复用其独立环境。

PowerShell 源码作为完整参数或 UTF-8 文件传入，不再嵌套本地 shell 拼接。工具处理中文、盘符和长脚本。

`run` 默认同步等待 60 秒，子命令前可加 `--timeout 120`。返回 124 表示远端结果未知，不自动重发；以退出码、日志、实际产物和必要的哈希判断结果。长任务断线保活需单独实现和确认。
