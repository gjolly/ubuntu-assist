#!/usr/bin/env python3
"""ubuntu-assist — an agentic CLI that answers Ubuntu questions using Claude and local system tools."""

import sys
import os
import json
import argparse
import tomllib
from pathlib import Path

import anthropic
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from tools import TOOLS_SCHEMA, execute_tool
from system_prompt import build_system_prompt

CONFIG_PATHS = [
    Path.home() / ".config" / "ubuntu-assist" / "config.toml",
    Path.home() / ".ubuntu-assist.toml",
]

console = Console()


def load_config() -> dict:
    for p in CONFIG_PATHS:
        if p.exists():
            with open(p, "rb") as f:
                return tomllib.load(f)
    return {}


def get_settings(config: dict) -> tuple[str, str]:
    api_key = config.get("api_key") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        console.print(
            "[bold red]Error:[/] No API key found.\n"
            "Set ANTHROPIC_API_KEY or add api_key to config file:\n"
            f"  {CONFIG_PATHS[0]}\n"
        )
        sys.exit(1)
    model = config.get("model", "claude-sonnet-4-20250514")
    return api_key, model


def print_tool_call(name: str, input_data: dict):
    """Show the user what tool the agent is calling."""
    summary = json.dumps(input_data, ensure_ascii=False)
    if len(summary) > 120:
        summary = summary[:117] + "..."
    console.print(f"  [dim]⚙ {name}[/dim] [dim italic]{summary}[/dim italic]")


def run_agent(question: str, api_key: str, model: str, verbose: bool = False):
    client = anthropic.Anthropic(api_key=api_key)
    system = build_system_prompt()

    messages = [{"role": "user", "content": question}]

    console.print()
    console.print("[bold cyan]Thinking…[/bold cyan]")

    max_iterations = 20
    for i in range(max_iterations):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=4096,
                system=system,
                tools=TOOLS_SCHEMA,
                messages=messages,
            )
        except anthropic.BadRequestError as e:
            console.print(f"\n[bold red]API error:[/] {e.message}")
            if "credit balance" in str(e.message).lower():
                console.print(
                    "[dim]Go to https://console.anthropic.com/settings/billing to add credits.[/dim]"
                )
            sys.exit(1)
        except anthropic.AuthenticationError:
            console.print("\n[bold red]Authentication failed.[/] Check your API key.")
            sys.exit(1)
        except anthropic.RateLimitError:
            console.print("\n[bold red]Rate limited.[/] Wait a moment and try again.")
            sys.exit(1)
        except anthropic.APIError as e:
            console.print(f"\n[bold red]API error:[/] {e.message}")
            sys.exit(1)
        except anthropic.APIConnectionError:
            console.print("\n[bold red]Connection error.[/] Check your internet connection.")
            sys.exit(1)

        # Collect assistant content blocks
        assistant_content = response.content

        # Check if there are any tool_use blocks
        tool_uses = [b for b in assistant_content if b.type == "tool_use"]

        if not tool_uses:
            # Final text response — print and exit
            text_parts = [b.text for b in assistant_content if b.type == "text"]
            full_text = "\n".join(text_parts)
            console.print()
            console.print(Markdown(full_text))
            console.print()
            return

        # There are tool calls — execute them all
        messages.append({"role": "assistant", "content": assistant_content})

        tool_results = []
        for tool_use in tool_uses:
            print_tool_call(tool_use.name, tool_use.input)
            result = execute_tool(tool_use.name, tool_use.input)
            if verbose:
                preview = result[:300] + "..." if len(result) > 300 else result
                console.print(f"    [dim]→ {preview}[/dim]")
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": result,
                }
            )

        messages.append({"role": "user", "content": tool_results})

    console.print("[yellow]Reached maximum iterations, stopping.[/yellow]")


def main():
    parser = argparse.ArgumentParser(
        prog="ubuntu-assist",
        description="Ask Ubuntu questions — answered by an AI agent with access to your system's manpages, packages, and files.",
    )
    parser.add_argument("question", nargs="*", help="Your question (or omit for interactive mode)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show tool outputs")
    parser.add_argument("--config", help="Path to config file (TOML)")
    args = parser.parse_args()

    config = {}
    if args.config:
        with open(args.config, "rb") as f:
            config = tomllib.load(f)
    else:
        config = load_config()

    api_key, model = get_settings(config)

    console.print(
        Panel(
            f"[bold]ubuntu-assist[/bold] — model: [cyan]{model}[/cyan]",
            border_style="blue",
        )
    )

    if args.question:
        question = " ".join(args.question)
        run_agent(question, api_key, model, verbose=args.verbose)
    else:
        # Interactive mode
        console.print("[dim]Interactive mode. Type 'exit' or Ctrl+C to quit.[/dim]\n")
        while True:
            try:
                question = console.input("[bold green]❯[/bold green] ")
                if question.strip().lower() in ("exit", "quit", "q"):
                    break
                if not question.strip():
                    continue
                run_agent(question, api_key, model, verbose=args.verbose)
            except (KeyboardInterrupt, EOFError):
                console.print("\n[dim]Bye.[/dim]")
                break


if __name__ == "__main__":
    main()
