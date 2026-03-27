"""Read-only system tools exposed to the Claude agent."""

import subprocess
import os

# Maximum bytes to return from any tool to avoid blowing up context
MAX_OUTPUT = 30_000


def _run(cmd: list[str], timeout: int = 15) -> str:
    """Run a command and return stdout+stderr, truncated."""
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = r.stdout + r.stderr
    except subprocess.TimeoutExpired:
        out = f"[Command timed out after {timeout}s]"
    except FileNotFoundError:
        out = f"[Command not found: {cmd[0]}]"
    except Exception as e:
        out = f"[Error: {e}]"
    if len(out) > MAX_OUTPUT:
        out = out[:MAX_OUTPUT] + f"\n\n[…truncated at {MAX_OUTPUT} bytes]"
    return out


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def tool_read_manpage(page: str, section: str | None = None) -> str:
    """Read a manpage. Optionally specify section (e.g. '5' for config files)."""
    cmd = ["man", "--no-justification", "--no-hyphenation"]
    # Force plain text with col to strip backspace formatting
    if section:
        cmd.append(section)
    cmd.append(page)
    try:
        p1 = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env={**os.environ, "MANWIDTH": "100", "COLUMNS": "100"})
        p2 = subprocess.Popen(["col", "-bx"], stdin=p1.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        p1.stdout.close()
        out, err = p2.communicate(timeout=10)
        result = out.decode("utf-8", errors="replace")
        if p1.wait() != 0 and not result.strip():
            return f"No manpage found for '{page}'" + (f" in section {section}" if section else "")
    except Exception as e:
        return f"Error reading manpage: {e}"
    if len(result) > MAX_OUTPUT:
        result = result[:MAX_OUTPUT] + f"\n\n[…truncated at {MAX_OUTPUT} bytes]"
    return result


def tool_search_manpages(query: str) -> str:
    """Search manpage descriptions (apropos)."""
    return _run(["apropos", query])


def tool_read_file(path: str, max_lines: int = 500) -> str:
    """Read a file the user can read. Text files only."""
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        return f"File not found: {path}"
    if not os.access(path, os.R_OK):
        return f"Permission denied: {path}"
    if os.path.isdir(path):
        return "Path is a directory. Use list_directory instead."
    try:
        with open(path, "r", errors="replace") as f:
            lines = []
            for i, line in enumerate(f):
                if i >= max_lines:
                    lines.append(f"\n[…truncated after {max_lines} lines]")
                    break
                lines.append(line)
        result = "".join(lines)
        if len(result) > MAX_OUTPUT:
            result = result[:MAX_OUTPUT] + f"\n\n[…truncated at {MAX_OUTPUT} bytes]"
        return result
    except Exception as e:
        return f"Error reading file: {e}"


def tool_grep_file(path: str, regexp: str, max_lines: int = 500) -> str:
    """Look for a regular expression in a file using grep."""
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        return f"File not found: {path}"
    if not os.access(path, os.R_OK):
        return f"Permission denied: {path}"
    if os.path.isdir(path):
        return "Path is a directory. Use list_directory instead."

    cmd = ["grep", regexp, path]
    result = _run(cmd, timeout=10)
    lines = result.strip().split("\n")
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [f"[…{len(lines) - max_lines} more results]"]
    return "\n".join(lines)


def tool_list_directory(path: str) -> str:
    """List directory contents."""
    path = os.path.expanduser(path)
    if not os.path.isdir(path):
        return f"Not a directory: {path}"
    return _run(["ls", "-la", path])


def tool_find_files(pattern: str, directory: str = "/", max_results: int = 50) -> str:
    """Find files matching a pattern."""
    cmd = ["find", directory, "-maxdepth", "5", "-name", pattern, "-readable"]
    result = _run(cmd, timeout=10)
    lines = result.strip().split("\n")
    if len(lines) > max_results:
        lines = lines[:max_results] + [f"[…{len(lines) - max_results} more results]"]
    return "\n".join(lines)


def tool_search_installed_packages(query: str) -> str:
    """Search installed packages (dpkg-query)."""
    return _run(["dpkg-query", "-l", f"*{query}*"])


def tool_search_available_packages(query: str) -> str:
    """Search available packages in apt cache."""
    return _run(["apt-cache", "search", query])


def tool_package_info(package: str) -> str:
    """Get detailed info about a package."""
    return _run(["apt-cache", "show", package])


def tool_search_snaps(query: str) -> str:
    """Search the snap store."""
    return _run(["snap", "find", query], timeout=20)


def tool_snap_info(snap_name: str) -> str:
    """Get detailed info about a snap."""
    return _run(["snap", "info", snap_name], timeout=20)


def tool_list_installed_snaps() -> str:
    """List installed snaps."""
    return _run(["snap", "list"])


def tool_systemctl_status(unit: str = "") -> str:
    """Check status of a systemd unit, or list all if no unit given."""
    if unit:
        return _run(["systemctl", "status", "--no-pager", "-l", unit])
    else:
        return _run(["systemctl", "list-units", "--no-pager", "--type=service", "--state=running"])


def tool_check_updates() -> str:
    """Check for available package updates."""
    return _run(["apt", "list", "--upgradable"], timeout=20)


def tool_system_info() -> str:
    """Get basic system information."""
    parts = []
    for label, cmd in [
        ("OS Release", ["cat", "/etc/os-release"]),
        ("Kernel", ["uname", "-a"]),
        ("Uptime", ["uptime"]),
        ("Disk", ["df", "-h", "/"]),
        ("Memory", ["free", "-h"]),
    ]:
        parts.append(f"=== {label} ===\n{_run(cmd)}")
    return "\n".join(parts)


def tool_which(command: str) -> str:
    """Find the location of a command."""
    return _run(["which", command])


def tool_journalctl(
    unit: str | None = None,
    lines: int = 100,
    priority: str | None = None,
    since: str | None = None,
    grep: str | None = None,
) -> str:
    """Query the systemd journal (journalctl)."""
    cmd = ["journalctl", "--no-pager", "-n", str(lines)]
    
    if unit:
        cmd.extend(["-u", unit])
    
    if priority:
        cmd.extend(["-p", priority])
    
    if since:
        cmd.extend(["--since", since])
    
    if grep:
        cmd.extend(["--grep", grep])
    
    return _run(cmd, timeout=30)


# ---------------------------------------------------------------------------
# Tool schema for the API
# ---------------------------------------------------------------------------

TOOLS_SCHEMA = [
    {
        "name": "read_manpage",
        "description": "Read a Unix/Linux manpage. Returns the full text of the manpage.",
        "input_schema": {
            "type": "object",
            "properties": {
                "page": {"type": "string", "description": "Manpage name, e.g. 'apt', 'iptables', 'sshd_config'"},
                "section": {"type": "string", "description": "Optional manpage section, e.g. '5' for file formats, '8' for admin commands"},
            },
            "required": ["page"],
        },
    },
    {
        "name": "search_manpages",
        "description": "Search manpage descriptions using apropos. Use this to discover relevant manpages for a topic.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search term, e.g. 'firewall', 'disk encryption', 'process management'"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "read_file",
        "description": "Read a text file from the filesystem. Use this to inspect config files, logs, scripts, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute or ~ path to the file"},
                "max_lines": {"type": "integer", "description": "Max lines to read (default 500)", "default": 500},
            },
            "required": ["path"],
        },
    },
    {
        "name": "grep_file",
        "description": "Look for a regular expression in a file using Grep. Use this to avoid reading entire large files and look for specific things in text files.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute or ~ path to the file"},
                "regexp": {"type": "string", "description": "The regular expression to pass the the grep command"},
                "max_lines": {"type": "integer", "description": "Max lines to read (default 500)", "default": 500},
            },
            "required": ["path", "regexp"],
        }
    },
    {
        "name": "list_directory",
        "description": "List contents of a directory with details.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "find_files",
        "description": "Find files matching a glob pattern (searched up to 5 levels deep).",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Filename glob pattern, e.g. '*.conf', 'nginx*'"},
                "directory": {"type": "string", "description": "Starting directory (default '/')", "default": "/"},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "search_installed_packages",
        "description": "Search installed deb packages by name.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Package name or partial name"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_available_packages",
        "description": "Search all available packages in apt repositories.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search term"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "package_info",
        "description": "Get detailed information about a specific apt package (description, version, dependencies).",
        "input_schema": {
            "type": "object",
            "properties": {
                "package": {"type": "string", "description": "Exact package name"},
            },
            "required": ["package"],
        },
    },
    {
        "name": "search_snaps",
        "description": "Search the snap store for available snaps.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search term"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "snap_info",
        "description": "Get detailed info about a specific snap package.",
        "input_schema": {
            "type": "object",
            "properties": {
                "snap_name": {"type": "string", "description": "Snap name"},
            },
            "required": ["snap_name"],
        },
    },
    {
        "name": "list_installed_snaps",
        "description": "List all installed snaps.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "systemctl_status",
        "description": "Check status of a systemd service, or list running services if no unit specified.",
        "input_schema": {
            "type": "object",
            "properties": {
                "unit": {"type": "string", "description": "Service unit name, e.g. 'ssh', 'nginx'. Omit to list running services.", "default": ""},
            },
        },
    },
    {
        "name": "check_updates",
        "description": "List available package updates.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "system_info",
        "description": "Get system information: OS version, kernel, uptime, disk, memory.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "which",
        "description": "Find the path of an executable command.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Command name"},
            },
            "required": ["command"],
        },
    },
    {
        "name": "journalctl",
        "description": "Query the systemd journal logs. View system and service logs with filtering options.",
        "input_schema": {
            "type": "object",
            "properties": {
                "unit": {"type": "string", "description": "Filter by systemd unit/service name, e.g. 'nginx.service', 'ssh'"},
                "lines": {"type": "integer", "description": "Number of lines to show (default 100)", "default": 100},
                "priority": {"type": "string", "description": "Filter by priority: 'emerg', 'alert', 'crit', 'err', 'warning', 'notice', 'info', 'debug' or numeric 0-7"},
                "since": {"type": "string", "description": "Show entries since this time, e.g. 'today', 'yesterday', '1 hour ago', '2024-03-27 10:00:00'"},
                "grep": {"type": "string", "description": "Filter log entries matching this pattern (case-insensitive)"},
            },
        },
    },
]


# Map tool names to functions
_DISPATCH = {
    "read_manpage": lambda args: tool_read_manpage(args["page"], args.get("section")),
    "search_manpages": lambda args: tool_search_manpages(args["query"]),
    "read_file": lambda args: tool_read_file(args["path"], args.get("max_lines", 500)),
    "grep_file": lambda args: tool_grep_file(args["path"], args["regexp"], args.get("max_lines", 500)),
    "list_directory": lambda args: tool_list_directory(args["path"]),
    "find_files": lambda args: tool_find_files(args["pattern"], args.get("directory", "/")),
    "search_installed_packages": lambda args: tool_search_installed_packages(args["query"]),
    "search_available_packages": lambda args: tool_search_available_packages(args["query"]),
    "package_info": lambda args: tool_package_info(args["package"]),
    "search_snaps": lambda args: tool_search_snaps(args["query"]),
    "snap_info": lambda args: tool_snap_info(args["snap_name"]),
    "list_installed_snaps": lambda args: tool_list_installed_snaps(),
    "systemctl_status": lambda args: tool_systemctl_status(args.get("unit", "")),
    "check_updates": lambda args: tool_check_updates(),
    "system_info": lambda args: tool_system_info(),
    "which": lambda args: tool_which(args["command"]),
    "journalctl": lambda args: tool_journalctl(
        args.get("unit"),
        args.get("lines", 100),
        args.get("priority"),
        args.get("since"),
        args.get("grep"),
    ),
}


def execute_tool(name: str, input_data: dict) -> str:
    fn = _DISPATCH.get(name)
    if not fn:
        return f"Unknown tool: {name}"
    try:
        return fn(input_data)
    except Exception as e:
        return f"Tool error: {e}"
