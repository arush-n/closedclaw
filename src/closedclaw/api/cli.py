"""
Closedclaw CLI Entry Point

Command-line interface for managing closedclaw.
"""

import sys
import socket
from pathlib import Path
from typing import Optional

try:
    import typer
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
except ImportError:
    print("Error: Required packages not installed.")
    print("Run: pip install typer[all] rich")
    sys.exit(1)

from closedclaw.api import __version__
from closedclaw.api.core.config import Settings, get_settings, init_closedclaw, CLOSEDCLAW_DIR

app = typer.Typer(
    name="closedclaw",
    help="Privacy-first AI memory middleware",
    no_args_is_help=True,
)
console = Console()


def _is_port_in_use(host: str, port: int) -> bool:
    """Return True if a TCP port is already bound."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def _print_startup_hints(exc: Exception, host: str, port: int, reload: bool) -> None:
    exc_type = type(exc).__name__
    message = str(exc)
    lower_message = message.lower()

    console.print()
    console.print(f"[bold red]Server failed to start:[/] {exc_type}: {message}")
    console.print("[bold]Troubleshooting hints:[/]")

    if "address already in use" in lower_message or "winerror 10048" in lower_message:
        console.print(f"- Port conflict on {host}:{port}. Try [dim]closedclaw serve --port {port + 1}[/].")
    if "permission" in lower_message or "access is denied" in lower_message:
        console.print("- Permission issue detected. Run in a terminal with sufficient permissions.")
    if "no module named" in lower_message:
        console.print("- Missing dependency/module. Reinstall project dependencies.")
    if "pydantic" in lower_message or "validation" in lower_message:
        console.print("- Configuration validation failed. Run [dim]closedclaw config list[/] and check values.")

    console.print("- Confirm config and token initialization: [dim]closedclaw init[/]")
    console.print("- Confirm server port availability before startup.")
    if reload:
        console.print("- If using --reload, retry without reload to isolate file-watcher issues.")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Server host"),
    port: int = typer.Option(8765, "--port", "-p", help="Server port"),
    reload: bool = typer.Option(False, "--reload", "-r", help="Enable hot-reload"),
    debug: bool = typer.Option(False, "--debug", "-d", help="Enable debug mode"),
    demo: bool = typer.Option(False, "--demo", help="Start with demo data"),
):
    """Start the closedclaw server."""
    console.print(Panel.fit(
        f"[bold green]closedclaw v{__version__}[/]\n"
        f"Your Memory. Your Rules. Your Machine.",
        title="🦞 Closedclaw",
    ))
    
    # Initialize
    settings = init_closedclaw()
    
    console.print(f"[dim]Config directory:[/] {settings.closedclaw_dir}")
    console.print(f"[dim]Provider:[/] {settings.provider}")
    console.print(f"[dim]Memory DB:[/] {settings.memory_db_path}")
    console.print()
    
    # Show endpoints
    console.print(f"[bold]API Server:[/] http://{host}:{port}")
    console.print(f"[bold]Dashboard:[/] http://{host}:{port}/app")
    console.print(f"[bold]OpenAI Proxy:[/] http://{host}:{port}/v1/chat/completions")
    console.print(f"[bold]API Docs:[/] http://{host}:{port}/docs")
    console.print()
    
    console.print("[dim]Press Ctrl+C to stop[/]")
    console.print()

    if settings.provider == "openai" and not settings.openai_api_key:
        console.print(
            "[yellow]Warning:[/] Provider is OpenAI but [dim]openai_api_key[/] is not configured. "
            "Proxy requests will fail until configured."
        )
        console.print()

    if _is_port_in_use(host, port):
        console.print(
            f"[bold red]Error:[/] Port {port} is already in use on {host}."
        )
        console.print(
            "Use a different port, e.g. [dim]closedclaw serve --port 8766[/], "
            "or stop the existing process first."
        )
        raise typer.Exit(code=1)
    
    # Load demo data if requested
    if demo:
        _load_demo_data()
    
    # Run server
    from closedclaw.api.app import run_server
    log_level = "debug" if debug else "info"
    try:
        run_server(host=host, port=port, reload=reload, log_level=log_level)
    except KeyboardInterrupt:
        console.print("\n[dim]Server stopped by user.[/]")
        raise typer.Exit(code=0)
    except Exception as exc:
        _print_startup_hints(exc, host=host, port=port, reload=reload)
        raise typer.Exit(code=1)


@app.command()
def init():
    """Initialize closedclaw configuration."""
    console.print("[bold]Initializing closedclaw...[/]")
    
    settings = init_closedclaw()
    token = settings.get_or_create_token()
    
    console.print(f"[green]✓[/] Config directory: {settings.closedclaw_dir}")
    console.print(f"[green]✓[/] Policies directory: {settings.policies_dir}")
    console.print(f"[green]✓[/] Audit directory: {settings.audit_dir}")
    console.print(f"[green]✓[/] Auth token generated")
    console.print()
    console.print("[bold]Next steps:[/]")
    console.print("1. Configure your LLM provider:")
    console.print("   [dim]closedclaw config set provider openai[/]")
    console.print("   [dim]closedclaw config set openai_api_key sk-...[/]")
    console.print()
    console.print("2. Start the server:")
    console.print("   [dim]closedclaw serve[/]")


@app.command()
def config(
    action: str = typer.Argument(..., help="Action: get, set, list"),
    key: Optional[str] = typer.Argument(None, help="Config key"),
    value: Optional[str] = typer.Argument(None, help="Config value"),
):
    """Manage closedclaw configuration."""
    settings = get_settings()
    
    if action == "list":
        table = Table(title="Closedclaw Configuration")
        table.add_column("Key", style="cyan")
        table.add_column("Value", style="green")
        
        for field_name, field_info in Settings.model_fields.items():
            current_value = getattr(settings, field_name, None)
            # Mask sensitive values
            if "key" in field_name.lower() or "token" in field_name.lower():
                if current_value:
                    current_value = f"{str(current_value)[:8]}..."
            table.add_row(field_name, str(current_value))
        
        console.print(table)
    
    elif action == "get":
        if not key:
            console.print("[red]Error: key is required for 'get' action[/]")
            raise typer.Exit(1)
        
        if hasattr(settings, key):
            value = getattr(settings, key)
            console.print(f"{key} = {value}")
        else:
            console.print(f"[red]Unknown config key: {key}[/]")
            raise typer.Exit(1)
    
    elif action == "set":
        if not key or value is None:
            console.print("[red]Error: key and value are required for 'set' action[/]")
            raise typer.Exit(1)
        
        if not hasattr(settings, key):
            console.print(f"[red]Unknown config key: {key}[/]")
            raise typer.Exit(1)
        
        # Update setting
        setattr(settings, key, value)
        settings.save()
        console.print(f"[green]✓[/] Set {key} = {value}")
    
    else:
        console.print(f"[red]Unknown action: {action}[/]")
        console.print("Use: get, set, or list")
        raise typer.Exit(1)


@app.command()
def status():
    """Show closedclaw status."""
    settings = get_settings()
    
    console.print(Panel.fit(
        f"[bold]closedclaw v{__version__}[/]",
        title="Status",
    ))
    
    # Check directories
    console.print(f"Config dir: {settings.closedclaw_dir} ", end="")
    console.print("[green]✓[/]" if settings.closedclaw_dir.exists() else "[red]✗[/]")
    
    # Check token
    token_file = settings.closedclaw_dir / "token"
    console.print(f"Auth token: ", end="")
    console.print("[green]✓[/]" if token_file.exists() else "[yellow]Not generated[/]")
    
    # Check provider
    console.print(f"Provider: {settings.provider}")
    
    # Check API key
    if settings.provider == "openai":
        has_key = bool(settings.openai_api_key)
        console.print(f"OpenAI API Key: ", end="")
        console.print("[green]✓ Configured[/]" if has_key else "[yellow]Not set[/]")
    elif settings.provider == "ollama":
        console.print(f"Ollama URL: {settings.ollama_base_url}")
    
    # Check memory DB
    console.print(f"Memory DB: {settings.memory_db_path} ", end="")
    console.print("[green]✓[/]" if settings.memory_db_path.exists() else "[dim]Not created yet[/]")


@app.command()
def token():
    """Show or regenerate the auth token."""
    settings = get_settings()
    token_value = settings.get_or_create_token()
    
    console.print(Panel.fit(
        f"[bold]{token_value}[/]",
        title="Auth Token",
    ))
    console.print()
    console.print("[dim]Use this token to authenticate API requests:[/]")
    console.print(f"  Authorization: Bearer {token_value}")
    console.print(f"  X-API-Key: {token_value}")


@app.command("export")
def export_data(
    output: Path = typer.Option(
        Path.home() / "closedclaw-export.json",
        "--output", "-o",
        help="Output file path"
    ),
    passphrase: str = typer.Option(
        ...,
        "--passphrase", "-p",
        prompt=True,
        hide_input=True,
        help="Encryption passphrase"
    ),
):
    """Export identity bundle (memories, policies, audit log)."""
    import json
    import hashlib
    from datetime import datetime, timezone
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    import os
    import base64

    console.print(f"[bold]Exporting to {output}...[/]")

    settings = get_settings()

    # Gather policies
    policies = []
    if settings.policies_dir.exists():
        for pf in settings.policies_dir.glob("*.json"):
            with open(pf) as f:
                policies.append(json.load(f))

    # Gather memory data (extended metadata from singleton)
    memory_data = []
    try:
        from closedclaw.api.core.memory import get_memory_instance
        mem = get_memory_instance()
        all_mems = mem.get_all(user_id="default")
        for m in all_mems.get("results", []):
            memory_data.append(m)
    except Exception as e:
        console.print(f"[yellow]Warning: Could not export memories: {e}[/]")

    # Bundle structure
    bundle = {
        "schema_version": "1.0",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "closedclaw_version": __version__,
        "memories": memory_data,
        "policies": policies,
    }

    # Serialize, then encrypt with AES-256-GCM
    plaintext = json.dumps(bundle, default=str).encode("utf-8")
    content_hash = hashlib.sha256(plaintext).hexdigest()

    salt = os.urandom(16)
    kdf = Scrypt(salt=salt, length=32, n=2**14, r=8, p=1)
    key = kdf.derive(passphrase.encode("utf-8"))

    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)

    wrapper = {
        "format": "closedclaw-identity-bundle",
        "schema_version": "1.0",
        "content_hash": content_hash,
        "salt": base64.b64encode(salt).decode(),
        "nonce": base64.b64encode(nonce).decode(),
        "ciphertext": base64.b64encode(ciphertext).decode(),
    }

    # Sign the wrapper (excluding signature field) with Ed25519
    try:
        from closedclaw.api.core.crypto import get_key_manager
        km = get_key_manager()
        wrapper_canonical = json.dumps(
            {k: v for k, v in wrapper.items()}, sort_keys=True
        ).encode()
        wrapper["ed25519_signature"] = km.sign(wrapper_canonical)
        wrapper["ed25519_pubkey"] = km.public_key_b64
    except Exception as e:
        console.print(f"[yellow]Warning: Could not sign bundle: {e}[/]")

    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        json.dump(wrapper, f, indent=2)

    console.print(f"[green]✓[/] Exported {len(memory_data)} memories, {len(policies)} policy sets")
    console.print(f"[green]✓[/] Bundle saved to {output}")
    console.print(f"[dim]Content hash: {content_hash[:16]}...[/]")


@app.command("import")
def import_data(
    input_file: Path = typer.Argument(..., help="Input bundle file"),
    passphrase: str = typer.Option(
        ...,
        "--passphrase", "-p",
        prompt=True,
        hide_input=True,
        help="Decryption passphrase"
    ),
):
    """Import identity bundle."""
    import json
    import hashlib
    import base64
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    console.print(f"[bold]Importing from {input_file}...[/]")

    if not input_file.exists():
        console.print(f"[red]Error: File not found: {input_file}[/]")
        raise typer.Exit(1)

    with open(input_file) as f:
        wrapper = json.load(f)

    if wrapper.get("format") != "closedclaw-identity-bundle":
        console.print("[red]Error: Not a valid closedclaw identity bundle[/]")
        raise typer.Exit(1)

    # Verify Ed25519 signature if present
    if wrapper.get("ed25519_signature") and wrapper.get("ed25519_pubkey"):
        try:
            from closedclaw.api.core.crypto import get_key_manager
            import base64 as _b64
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            km = get_key_manager()
            sig_fields = {k: v for k, v in wrapper.items()
                         if k not in ("ed25519_signature", "ed25519_pubkey")}
            canonical = json.dumps(sig_fields, sort_keys=True).encode()
            if not km.verify(canonical, wrapper["ed25519_signature"]):
                console.print("[yellow]Warning: Ed25519 signature mismatch — bundle may not be from this identity[/]")
            else:
                console.print("[green]✓[/] Ed25519 bundle signature verified")
        except Exception as e:
            console.print(f"[yellow]Warning: Could not verify bundle signature: {e}[/]")
    else:
        console.print("[yellow]Note: Bundle has no Ed25519 signature (older format)[/]")

    # Decrypt
    salt = base64.b64decode(wrapper["salt"])
    nonce = base64.b64decode(wrapper["nonce"])
    ciphertext = base64.b64decode(wrapper["ciphertext"])

    kdf = Scrypt(salt=salt, length=32, n=2**14, r=8, p=1)
    key = kdf.derive(passphrase.encode("utf-8"))

    aesgcm = AESGCM(key)
    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    except Exception:
        console.print("[red]Error: Decryption failed — wrong passphrase or corrupted bundle[/]")
        raise typer.Exit(1)

    # Verify hash
    content_hash = hashlib.sha256(plaintext).hexdigest()
    if content_hash != wrapper.get("content_hash"):
        console.print("[red]Error: Content hash mismatch — bundle may be tampered with[/]")
        raise typer.Exit(1)

    bundle = json.loads(plaintext.decode("utf-8"))
    console.print(f"[green]✓[/] Bundle decrypted and verified")
    console.print(f"[dim]Schema: {bundle.get('schema_version')}, Exported: {bundle.get('exported_at')}[/]")

    settings = get_settings()
    settings.ensure_directories()

    # Import policies
    policies = bundle.get("policies", [])
    for i, policy in enumerate(policies):
        policy_file = settings.policies_dir / f"imported_{i}.json"
        with open(policy_file, "w") as f:
            json.dump(policy, f, indent=2)

    # Import memories
    memories = bundle.get("memories", [])
    imported_count = 0
    try:
        from closedclaw.api.core.memory import get_memory_instance
        mem = get_memory_instance()
        for m in memories:
            content = m.get("memory", m.get("content", ""))
            if content:
                mem.add(
                    content=content,
                    user_id=m.get("user_id", "default"),
                    sensitivity=m.get("sensitivity"),
                    tags=m.get("tags", []),
                    source="imported",
                )
                imported_count += 1
    except Exception as e:
        console.print(f"[yellow]Warning: Could not import some memories: {e}[/]")

    console.print(f"[green]✓[/] Imported {imported_count} memories, {len(policies)} policy sets")


@app.command()
def version():
    """Show version information."""
    console.print(f"closedclaw v{__version__}")


def _load_demo_data():
    """Load demo data into memory."""
    console.print("[dim]Loading demo data...[/]")
    
    from closedclaw.api.core.memory import get_memory_instance
    
    memory = get_memory_instance()
    
    demo_memories = [
        {
            "content": "User's name is Alex and they work as a software engineer.",
            "sensitivity": 1,
            "tags": ["personal", "work"],
            "source": "conversation",
        },
        {
            "content": "User prefers dark mode and uses VS Code as their primary editor.",
            "sensitivity": 0,
            "tags": ["preferences", "tools"],
            "source": "conversation",
        },
        {
            "content": "User is working on a privacy-focused AI project called closedclaw.",
            "sensitivity": 1,
            "tags": ["work", "projects"],
            "source": "conversation",
        },
        {
            "content": "User has been experiencing stress about work deadlines.",
            "sensitivity": 2,
            "tags": ["health", "work"],
            "source": "conversation",
        },
        {
            "content": "User's home address is 123 Privacy Lane, Austin TX.",
            "sensitivity": 3,
            "tags": ["personal", "address"],
            "source": "manual",
        },
    ]
    
    for mem in demo_memories:
        try:
            memory.add(**mem)
        except Exception as e:
            console.print(f"[yellow]Warning: Could not add demo memory: {e}[/]")
    
    console.print(f"[green]✓[/] Loaded {len(demo_memories)} demo memories")


def main():
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
