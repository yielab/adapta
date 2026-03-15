"""Command-line interface for Brain"""

import click
import sys
import asyncio
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from brain import __version__
from brain.config import settings

console = Console()


@click.group()
@click.version_option(__version__)
def main():
    """Brain From Cero - Local AI Brain CLI"""
    pass


@main.command()
@click.option("--host", default=settings.host, help="Host to bind to")
@click.option("--port", default=settings.port, help="Port to bind to")
@click.option("--reload", is_flag=True, help="Enable auto-reload")
def start(host, port, reload):
    """Start the Brain server"""
    import uvicorn

    console.print(Panel.fit(
        f"[bold blue]🧠 Brain From Cero v{__version__}[/bold blue]\n"
        f"Starting server on [cyan]http://{host}:{port}[/cyan]\n"
        f"Dashboard: [cyan]http://{host}:{port}/dashboard[/cyan]\n"
        f"API: [cyan]http://{host}:{port}/v1[/cyan]",
        title="Brain Server",
        border_style="blue"
    ))

    uvicorn.run(
        "brain.server:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


@main.command()
def models():
    """List available models"""
    from brain.core import model_manager

    table = Table(title="Available Models", show_header=True, header_style="bold blue")
    table.add_column("Name", style="cyan")
    table.add_column("Type", style="green")
    table.add_column("Status", style="yellow")
    table.add_column("Path")

    models_list = model_manager.list_models()

    for model in models_list:
        status = "✓ Downloaded" if model.path.exists() else "✗ Not Downloaded"
        status_style = "green" if model.path.exists() else "red"
        table.add_row(
            model.name,
            model.model_type.value,
            f"[{status_style}]{status}[/{status_style}]",
            str(model.path)
        )

    console.print(table)


@main.command()
@click.argument("model_name")
def download(model_name):
    """Download a model (shows instructions)"""
    from brain.core import model_manager

    config = model_manager.get_model_config(model_name)

    if not config:
        console.print(f"[red]Error: Unknown model '{model_name}'[/red]")
        console.print("\nAvailable models:")
        for m in model_manager.list_models():
            console.print(f"  • {m.name}")
        sys.exit(1)

    if config.path.exists():
        console.print(f"[green]Model {model_name} is already downloaded![/green]")
        return

    # Show download instructions
    console.print(Panel.fit(
        f"[bold]Download Instructions for {model_name}[/bold]\n\n"
        f"The model needs to be downloaded manually using Hugging Face CLI:\n\n"
        f"[cyan]1. Install Hugging Face CLI:[/cyan]\n"
        f"   pip install huggingface-hub\n\n"
        f"[cyan]2. Download the model:[/cyan]\n"
        f"   huggingface-cli download MODEL_REPO MODEL_FILE --local-dir {config.path.parent}\n\n"
        f"[yellow]Model will be saved to:[/yellow]\n"
        f"   {config.path}\n\n"
        f"[dim]For specific download commands, check the MLOps plan.[/dim]",
        title="Download Model",
        border_style="blue"
    ))


@main.command()
def agents():
    """List all agents"""
    async def _list_agents():
        from brain.agents import agent_manager
        await agent_manager.load_agents()

        agents_list = agent_manager.list_agents()

        if not agents_list:
            console.print("[yellow]No agents created yet[/yellow]")
            console.print("\nCreate an agent with: [cyan]brain create-agent[/cyan]")
            return

        table = Table(title="Agents", show_header=True, header_style="bold blue")
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Model", style="yellow")
        table.add_column("Capabilities")

        for agent in agents_list:
            caps = ", ".join(agent.capabilities[:3])
            if len(agent.capabilities) > 3:
                caps += "..."
            table.add_row(agent.id, agent.name, agent.model, caps)

        console.print(table)

    asyncio.run(_list_agents())


@main.command()
@click.option("--name", prompt="Agent name", help="Name of the agent")
@click.option("--template", default="general", help="Template to use (general, code_expert, vision_analyst)")
@click.option("--model", help="Model to use (optional, uses template default)")
def create_agent(name, template, model):
    """Create a new agent"""
    async def _create():
        from brain.agents import agent_manager
        await agent_manager.load_agents()

        try:
            agent = await agent_manager.create_agent(
                name=name,
                template=template,
                model=model,
            )
            console.print(f"[green]✓ Created agent: {agent.name} ({agent.id})[/green]")
            console.print(f"Model: {agent.model}")
            console.print(f"Capabilities: {', '.join(agent.capabilities)}")
        except Exception as e:
            console.print(f"[red]Error creating agent: {e}[/red]")
            sys.exit(1)

    asyncio.run(_create())


@main.command()
@click.argument("agent_id")
def delete_agent(agent_id):
    """Delete an agent"""
    async def _delete():
        from brain.agents import agent_manager
        await agent_manager.load_agents()

        if click.confirm(f"Are you sure you want to delete agent '{agent_id}'?"):
            success = await agent_manager.delete_agent(agent_id)
            if success:
                console.print(f"[green]✓ Deleted agent: {agent_id}[/green]")
            else:
                console.print(f"[red]Error: Agent not found[/red]")
                sys.exit(1)

    asyncio.run(_delete())


@main.command()
def templates():
    """List available agent templates"""
    from brain.agents.templates import AGENT_TEMPLATES

    table = Table(title="Agent Templates", show_header=True, header_style="bold blue")
    table.add_column("Template", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Default Model", style="yellow")
    table.add_column("Capabilities")

    for key, template in AGENT_TEMPLATES.items():
        caps = ", ".join(template["capabilities"][:3])
        if len(template["capabilities"]) > 3:
            caps += "..."
        table.add_row(
            key,
            template["name"],
            template["model"],
            caps
        )

    console.print(table)


@main.command()
def config():
    """Show current configuration"""
    table = Table(title="Configuration", show_header=True, header_style="bold blue")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")

    config_items = [
        ("Data Directory", str(settings.data_dir)),
        ("Models Directory", str(settings.models_dir)),
        ("Agents Directory", str(settings.agents_dir)),
        ("Default Model", settings.default_model),
        ("Embedding Model", settings.embedding_model),
        ("Host", settings.host),
        ("Port", str(settings.port)),
        ("GPU Layers", str(settings.n_gpu_layers)),
        ("Threads", str(settings.n_threads)),
    ]

    for key, value in config_items:
        table.add_row(key, value)

    console.print(table)


@main.command()
def info():
    """Show system information"""
    import platform
    import torch

    console.print(Panel.fit(
        f"[bold blue]🧠 Brain From Cero[/bold blue]\n\n"
        f"[cyan]Version:[/cyan] {__version__}\n"
        f"[cyan]Python:[/cyan] {platform.python_version()}\n"
        f"[cyan]Platform:[/cyan] {platform.system()} {platform.machine()}\n"
        f"[cyan]PyTorch:[/cyan] {torch.__version__}\n"
        f"[cyan]CUDA Available:[/cyan] {torch.cuda.is_available()}\n"
        f"[cyan]Data Directory:[/cyan] {settings.data_dir}\n",
        title="System Information",
        border_style="blue"
    ))


if __name__ == "__main__":
    main()
