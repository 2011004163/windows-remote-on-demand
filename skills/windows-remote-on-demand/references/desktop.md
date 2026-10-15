# 按需桌面入口

调用本 Skill 的 `scripts/windows_desktop.py`。首次部署由使用者完成；不要在每次桌面任务前运行 `setup`。需要已登录且可访问的 Windows 桌面。

```bash
python3 <skill-root>/scripts/windows_desktop.py start
python3 <skill-root>/scripts/windows_desktop.py tools
python3 <skill-root>/scripts/windows_desktop.py describe Snapshot
python3 <skill-root>/scripts/windows_desktop.py call Snapshot --args '{"use_vision":false}'
python3 <skill-root>/scripts/windows_desktop.py stop
```

`tools` 只给出名称；按需 `describe` 将使用的工具，再按照真实 schema 调用。先观察最新画面或 UI 元素，不沿用旧坐标。只看文字时不请求图像；需要图像时，读取工具返回的本地文件路径，不向上下文打印 base64。

任务结束、失败或放弃时调用 `stop`，确认 `stopped=true`。300 秒空闲退出只是中断兜底。命令和文件任务不启动桌面服务，也不需要在 AI 客户端注册常驻 MCP。

失败或超时后先重新观察状态，不自动重放点击或输入。单控制端使用，不与其他人共用同一部署；不要对运行中的会话执行 `setup`。锁屏、UAC、注销及重启未登录不在当前验收范围。
