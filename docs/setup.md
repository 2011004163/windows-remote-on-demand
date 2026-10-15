# 安装与连接

本指南按单个 Mac 控制单个 Windows 账户组织。已有 SSH / Windows-MCP 环境可直接复用，不需要重装。

## 1. Tailscale 连接两台机器

两端安装 Tailscale 并加入同一个网络。记下两端 Tailscale IPv4 地址，确认能互相访问。地址、账户和设备名仅留在你自己的配置中。

Windows 需要注销后仍保持网络客户端运行时，可开启 Run unattended。该选项不会创建已登录的交互桌面。双机直接连接不需要出口节点或子网路由；如关闭 Tailscale DNS，后续使用固定 IP，不依赖 MagicDNS 名称。

## 2. 专用公钥与 Windows OpenSSH

Mac 生成专用密钥；私钥只留在 Mac，公钥可以通过 Taildrop 发送到 Windows：

```bash
ssh-keygen -t ed25519 -f ~/.ssh/windows_remote_ed25519 -C windows-remote-client
```

密钥设置了口令时，先将它加载到本机 SSH agent，供非交互任务使用。不要把私钥、密钥口令或已有账户密码放进仓库。

在 Windows 的管理员 PowerShell 中运行以下模板，替换三个参数：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\skills\windows-remote-on-demand\scripts\windows\enable-openssh.ps1 -ControllerIp "CONTROLLER_TAILSCALE_IP" -WindowsIp "WINDOWS_TAILSCALE_IP" -PublicKeyFile "C:\path\to\windows_remote_ed25519.pub"
```

该辅助脚本沿用已成功的安装流程：安装缺少的 OpenSSH Server、追加限定来源 IP 的公钥、备份原设置、把默认 SSH 防火墙规则限定到控制端地址、启动 sshd 并设为自动启动。它适用于本地管理员账户和 Windows 默认管理员公钥规则；非管理员账户、Entra 账户、自定义 sshd 配置或多控制端环境，请按 Microsoft 文档调整，不要照搬。

脚本不会删除已有公钥，但会改变默认 SSH 防火墙规则的来源范围。若该规则原来服务其他客户端，先判断影响。备份位置会显示在 Windows 本机。其他已有允许 SSH 的防火墙规则仍需自行核对。

脚本会在 Windows 本机显示主机公钥指纹，并尝试通过 Taildrop 发送连接报告给指定控制端。报告含设备信息，只能私下保存，不要提交到公开仓库。

## 3. 核对并固定主机指纹

复制 [SSH 模板](../examples/ssh-config.example) 到 `~/.ssh/windows_remote.conf`，替换 `HostName` 和 `User`。用户名用 Windows 中实际 `whoami` 对应的本地登录账户。

在 Mac 收集候选主机公钥：

```bash
ssh-keyscan -t ed25519 WINDOWS_TAILSCALE_IP > ~/.ssh/windows_remote_known_hosts.candidate
ssh-keygen -lf ~/.ssh/windows_remote_known_hosts.candidate
```

将候选指纹与 Windows 本机或可信私下回传的指纹比较，**一致后** 才保存到 `~/.ssh/windows_remote_known_hosts`。`ssh-keyscan` 本身不证明身份。客户端保持 `StrictHostKeyChecking yes`，不要用关闭校验的方法绕过错误。

```bash
ssh -F ~/.ssh/windows_remote.conf windows-remote whoami
python3 tools/windows_remote.py info
```

返回的账户和电脑应与你配置的目标一致。上传文件前，在 Windows 建立目标父目录。

## 4. Windows-MCP 独立安装或复用

如果只需要命令和文件，可以在这里停止。桌面操作才需要 Windows-MCP。

在 Windows 安装官方 uv，或复用已有 uv。在 Windows PowerShell 执行：

```powershell
$runtime = Join-Path $env:LOCALAPPDATA 'WindowsRemote\WindowsMCP'
New-Item -ItemType Directory -Force -Path $runtime | Out-Null
uv venv --python 3.14 --managed-python (Join-Path $runtime 'venv')
uv pip install --python (Join-Path $runtime 'venv\Scripts\python.exe') 'windows-mcp==0.8.8'
```

这使用独立 Python 和依赖，不修改已有项目环境。只固定已验证的 Windows-MCP 版本，其他依赖由安装器解析。已有可用环境时不要再运行创建命令；在 Mac 侧 [桌面脚本](../skills/windows-remote-on-demand/scripts/windows_desktop.py) 的 `setup()` 函数末尾找到包含 `RuntimeRoot` 的调用，将其中路径改为现有环境的父目录，保持其中存在 `venv\Scripts\windows-mcp.exe`。

默认控制目录是 `D:\RemoteWork\Tools\Windows-MCP`。没有 D 盘时，可修改 Mac 侧脚本顶部 `ROOT` 为自己选择的专用目录。不要设置成盘根目录、共享资料目录或不属于本项目的已有目录：`setup` 会收紧该目录的访问权限。

## 5. 从 Mac 部署按需入口

Windows 用户保持登录，在 Mac 仓库根目录执行一次：

```bash
python3 tools/windows_desktop.py setup
python3 tools/windows_desktop.py start
python3 tools/windows_desktop.py tools
python3 tools/windows_desktop.py call ControlStatus
python3 tools/windows_desktop.py stop
```

`setup` 生成两端私密认证配置，上传两个 PowerShell 入口，创建**没有登录触发器**的交互任务；不会启动它。`start` 才建立回环 HTTP 服务和严格校验的 SSH 转发。无需把服务器加入 Codex / Claude 的常驻 MCP 配置。

`stop` 返回 `stopped=true`，`status` 显示无 Windows 进程且 `tunnelRunning=false`，表示结束。Windows 日志在 `ROOT` 指定目录；端点为 `/mcp`，不是 `/mcp/`。

## 6. 给 AI 代理安装 Skill（可选）

`skills/windows-remote-on-demand` 是自包含 Skill：正文、脚本和 Windows 资源在同一目录。可以用你的客户端 Skill 安装功能安装该目录，或复制到客户端的 Skill 目录，保留完整目录结构。不要覆盖同名的已有技能。

Skill 会让代理先用命令/文件入口，只有需要看窗口或操作界面时才读取桌面参考与工具说明。无需为每个任务重新加载安装说明。
