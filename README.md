# ubuntu-assist

An agentic CLI that answers Ubuntu/Linux questions by investigating your actual system — reading manpages, checking installed packages, inspecting config files, and querying snap/apt repos — then answering with context-aware advice powered by Claude.

## How it works

You ask a question. The agent doesn't just guess — it uses tools to investigate your system:

```
╭───────────────────────────────────────────────────────────────────────────────────────────────────╮
│ ubuntu-assist — model: claude-sonnet-4-20250514                                                   │
╰───────────────────────────────────────────────────────────────────────────────────────────────────╯
Interactive mode. Type 'exit' or Ctrl+C to quit.

❯ is my system up to date?

Thinking…
  ⚙ check_updates {}

Your system is not fully up to date. There are 12 packages that can be updated:

Available Updates:

 • alsa-ucm-conf - Audio configuration updates
 • bind9-dnsutils, bind9-host, bind9-libs - DNS utilities security updates
 • code - Visual Studio Code (1.112.0 → 1.113.0)
 • devscripts - Development scripts
 • gdm3, gir1.2-gdm-1.0, libgdm1 - GNOME Display Manager updates
 • google-chrome-stable - Chrome browser (146.0.7680.153 → 146.0.7680.164)
 • terraform - Infrastructure tool (1.14.7 → 1.14.8)
 • ubuntu-drivers-common - Driver management updates

To update your system:


 sudo apt update && sudo apt upgrade


The updates include security patches (bind9 packages) and regular software updates. I recommend
applying these updates to keep your system secure and current.
```

The agent can chain multiple tool calls per question, deciding on the fly what to look up.

## Install

**Requirements:** Python 3.11+, an Anthropic API key.

```bash
# Clone or copy the ubuntu-assist directory
pip install anthropic rich

# Make it executable
chmod +x ubuntu-assist

# Optional: symlink to PATH
ln -s $(pwd)/ubuntu-assist ~/.local/bin/ubuntu-assist
```

## Configure

Create `~/.config/ubuntu-assist/config.toml`:

```toml
api_key = "sk-ant-your-key-here"
model = "claude-sonnet-4-20250514"
```

Or just export `ANTHROPIC_API_KEY` and the default model (Sonnet) will be used.

## Usage

```bash
# Single question
./ubuntu-assist "How do I check which ports are open?"

# Interactive mode (no arguments)
./ubuntu-assist

# Verbose mode — see tool outputs
./ubuntu-assist -v "What version of OpenSSL do I have?"

# Custom config
./ubuntu-assist --config /path/to/config.toml "What services are running?"
```

## Available tools

The agent has access to these read-only tools:

| Tool | What it does |
|---|---|
| `read_manpage` | Read any manpage (with optional section) |
| `search_manpages` | Search manpage descriptions (apropos) |
| `read_file` | Read any file the user can access |
| `list_directory` | List directory contents |
| `find_files` | Find files by glob pattern |
| `search_installed_packages` | Search installed deb packages |
| `search_available_packages` | Search apt repositories |
| `package_info` | Detailed apt package info |
| `search_snaps` | Search the snap store |
| `snap_info` | Detailed snap info |
| `list_installed_snaps` | List installed snaps |
| `systemctl_status` | Check service status |
| `check_updates` | List available updates |
| `system_info` | OS, kernel, disk, memory info |
| `which` | Locate a command |
| `run_command` | Run arbitrary read-only shell commands |

All tools are strictly read-only. The `run_command` tool blocks write operations, sudo, network downloads, and script execution.

## Example questions

- "How do I install Docker?"
- "What's using port 8080?"
- "Explain my SSH config"
- "How do I set up automatic updates?"
- "What filesystem am I using and how full is it?"
- "How do I add a cron job that runs every Monday?"
- "Is nginx installed? How is it configured?"

## Cost

Each question typically uses 3-8 tool calls, which with Sonnet costs roughly $0.01-0.05 per question. Complex investigations with many tool calls may cost more.
