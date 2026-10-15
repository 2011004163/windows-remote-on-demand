# Windows Remote On Demand

A practical macOS → Windows workflow using Tailscale, native Windows OpenSSH, and optional Windows-MCP desktop tools.

- Commands and file transfers use Python's standard library plus OpenSSH.
- Desktop tools start only on demand inside the logged-in Windows user's interactive session.
- The desktop service binds to Windows loopback and is reached through an SSH tunnel.
- No login trigger and no permanently registered MCP tool list in the AI client.
- Close desktop access at task completion; a 300-second idle timeout is a fallback.
- Full tool schemas and screenshots are still context when used; this is not a zero-token claim.

The baseline workflow was exercised on macOS and Windows 11: pinned host-key authentication, UTF-8 PowerShell output, exit codes, long scripts, Unicode/space paths, binary round-trip hashes, MCP initialization and tool discovery, read-only control/display calls, authentication rejection, and shutdown/idle expiry. Mouse/keyboard actions, lock-screen/UAC interaction, cross-network operation, unattended reboot behavior, long-running compute survival, and GPU workloads are not covered by that verification.

This public copy changes private names/paths into neutral defaults and templates. It does not include private keys, real addresses, account names, machine fingerprints, personal logs, screenshots or workspace Git history.

See the [Chinese setup guide](setup.md) and [privacy / cleanup notes](privacy.md). Install the self-contained `skills/windows-remote-on-demand` directory if you want an AI agent to route between command/file access and on-demand desktop access. The default desktop runtime expects Windows-MCP 0.8.8 in a dedicated Python 3.14 environment. Existing installations can be reused by changing the documented path.

This is a single-controller personal workflow, not a multi-user remote-control platform or an unattended job scheduler. It does not promise compatibility with every Windows/SSH configuration.

MIT applies to this repository's code. [Windows-MCP](https://github.com/CursorTouch/Windows-MCP), Tailscale and OpenSSH are separate dependencies with their own licenses and terms.
