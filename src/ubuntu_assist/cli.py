#!/usr/bin/env python3
"""ubuntu-assist — an agentic CLI that answers Ubuntu questions using Claude and local system tools."""

import sys
import os
import json
import argparse
import getpass
import tomllib
from pathlib import Path

import anthropic
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from ubuntu_assist.tools import TOOLS_SCHEMA, execute_tool
from ubuntu_assist.system_prompt import build_system_prompt

CONFIG_PATH = Path.home() / ".config" / "ubuntu-assist" / "config.toml"

MODELS = [
    ("claude-sonnet-4-20250514", "Sonnet 4 — fast, good for most queries"),
    ("claude-opus-4-20250514", "Opus 4 — most capable, slower, pricier"),
    ("claude-haiku-4-5-20251001", "Haiku 4.5 — fastest, cheapest"),
]
DEFAULT_MODEL = MODELS[0][0]

console = Console()


def load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "rb") as f:
            return tomllib.load(f)
    return {}


def run_setup() -> dict:
    """Interactive first-run setup — prompts for API key and model, writes config."""
    console.print(
        Panel(
            "[bold]Welcome to ubuntu-assist![/bold]\n"
            "Let's set up your configuration.",
            border_style="blue",
        )
    )

    console.print("\nYou'll need an Anthropic API key.")
    console.print("[dim]Get one at https://console.anthropic.com/settings/keys[/dim]\n")
    api_key = getpass.getpass("API key: ").strip()
    if not api_key:
        console.print("[bold red]No API key provided. Exiting.[/bold red]")
        sys.exit(1)

    console.print("\n[bold]Choose a model:[/bold]")
    for i, (model_id, description) in enumerate(MODELS, 1):
        marker = " [cyan](default)[/cyan]" if i == 1 else ""
        console.print(f"  {i}. {model_id} — {description}{marker}")
    choice = console.input(f"\nModel number [bold][1][/bold]: ").strip()
    if choice in ("", "1"):
        model = MODELS[0][0]
    elif choice in (str(i) for i in range(2, len(MODELS) + 1)):
        model = MODELS[int(choice) - 1][0]
    else:
        console.print(f"[yellow]Invalid choice '{choice}', using default.[/yellow]")
        model = DEFAULT_MODEL

    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        f.write(f'api_key = "{api_key}"\n')
        f.write(f'model = "{model}"\n')

    console.print(f"\n[green]Config saved to {CONFIG_PATH}[/green]\n")
    return {"api_key": api_key, "model": model}


def get_settings(config: dict) -> tuple[str, str]:
    api_key = config.get("api_key") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        config = run_setup()
        api_key = config["api_key"]
    model = config.get("model", DEFAULT_MODEL)
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
    args = parser.parse_args()

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
