#!/usr/bin/env python3
"""Verify Brain setup and configuration"""

import sys
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()


def check_dependencies():
    """Check if required dependencies are installed"""
    deps = {
        "fastapi": "FastAPI",
        "uvicorn": "Uvicorn",
        "llama_cpp": "llama-cpp-python",
        "chromadb": "ChromaDB",
        "sentence_transformers": "Sentence Transformers",
        "pydantic": "Pydantic",
        "click": "Click",
        "rich": "Rich",
    }

    missing = []
    for module, name in deps.items():
        try:
            __import__(module)
            status = "[green]✓[/green]"
        except ImportError:
            status = "[red]✗[/red]"
            missing.append(name)

    table = Table(title="Dependencies", show_header=True, header_style="bold blue")
    table.add_column("Package", style="cyan")
    table.add_column("Status", justify="center")

    for module, name in deps.items():
        try:
            __import__(module)
            status = "[green]✓ Installed[/green]"
        except ImportError:
            status = "[red]✗ Missing[/red]"
        table.add_row(name, status)

    console.print(table)
    return missing


def check_directories():
    """Check if required directories exist"""
    dirs = {
        "data": Path("data"),
        "data/models": Path("data/models"),
        "data/agents": Path("data/agents"),
        "data/cache": Path("data/cache"),
    }

    table = Table(title="Directories", show_header=True, header_style="bold blue")
    table.add_column("Directory", style="cyan")
    table.add_column("Status", justify="center")

    all_exist = True
    for name, path in dirs.items():
        if path.exists():
            status = "[green]✓ Exists[/green]"
        else:
            status = "[yellow]⚠ Missing (will be created)[/yellow]"
            all_exist = False
        table.add_row(str(path), status)

    console.print(table)
    return all_exist


def check_models():
    """Check if any models are downloaded"""
    models_dir = Path("data/models")
    if not models_dir.exists():
        console.print("[yellow]Models directory doesn't exist yet[/yellow]")
        return []

    found_models = []
    for model_file in models_dir.rglob("*.gguf"):
        found_models.append(model_file)

    table = Table(title="Models", show_header=True, header_style="bold blue")
    table.add_column("Model File", style="cyan")
    table.add_column("Size", justify="right")

    if found_models:
        for model in found_models:
            size_mb = model.stat().st_size / (1024 * 1024)
            table.add_row(str(model.relative_to(models_dir)), f"{size_mb:.1f} MB")
    else:
        table.add_row("[yellow]No models found[/yellow]", "")

    console.print(table)
    return found_models


def main():
    console.print(
        Panel.fit(
            "[bold blue]🧠 Brain From Cero - Setup Verification[/bold blue]",
            border_style="blue",
        )
    )
    console.print()

    # Check dependencies
    console.print("[bold]1. Checking Dependencies...[/bold]")
    missing_deps = check_dependencies()
    console.print()

    if missing_deps:
        console.print(
            f"[red]⚠ Missing dependencies: {', '.join(missing_deps)}[/red]"
        )
        console.print("[yellow]Install with: pip install -r requirements.txt[/yellow]")
        console.print()

    # Check directories
    console.print("[bold]2. Checking Directories...[/bold]")
    check_directories()
    console.print()

    # Check models
    console.print("[bold]3. Checking Models...[/bold]")
    models = check_models()
    console.print()

    if not models:
        console.print("[yellow]⚠ No models found![/yellow]")
        console.print()
        console.print("[bold]To download models:[/bold]")
        console.print("1. Install Hugging Face CLI: [cyan]pip install huggingface-hub[/cyan]")
        console.print()
        console.print("2. Download a model (example):")
        console.print(
            "[cyan]huggingface-cli download Qwen/Qwen2.5-3B-Instruct-GGUF "
            "qwen2.5-3b-instruct-q4_k_m.gguf --local-dir ./data/models/qwen2.5-3b[/cyan]"
        )
        console.print()
        console.print("See README.md for more model options.")
        console.print()

    # Summary
    if not missing_deps and models:
        console.print(
            Panel.fit(
                "[green]✓ Setup looks good! Ready to start.[/green]\n\n"
                "Run: [cyan]brain start[/cyan] or [cyan]./start.sh[/cyan]",
                title="Status",
                border_style="green",
            )
        )
        return 0
    elif not missing_deps:
        console.print(
            Panel.fit(
                "[yellow]⚠ Setup incomplete - download models first[/yellow]\n\n"
                "See instructions above.",
                title="Status",
                border_style="yellow",
            )
        )
        return 1
    else:
        console.print(
            Panel.fit(
                "[red]✗ Setup incomplete - install dependencies first[/red]\n\n"
                "Run: [cyan]pip install -r requirements.txt[/cyan]",
                title="Status",
                border_style="red",
            )
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
