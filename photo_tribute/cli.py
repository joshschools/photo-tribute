"""CLI entry point for photo-tribute."""

import click

from photo_tribute.state import State


@click.group()
def cli():
    """photo-tribute: restore correct dates to Google Photos after an iCloud migration."""


@cli.command()
@click.option("--icloud-user", envvar="ICLOUD_USERNAME", required=True, help="Apple ID email")
@click.option("--icloud-pass", envvar="ICLOUD_PASSWORD", default=None, help="Apple ID password (or set ICLOUD_PASSWORD)")
def auth(icloud_user, icloud_pass):
    """Authenticate with iCloud once and save session cookie (~2 month TTL)."""
    import subprocess
    cmd = [
        "icloudpd",
        "--username", icloud_user,
        "--cookie-directory", ".icloud-session",
        "--auth-only",
    ]
    if icloud_pass:
        cmd += ["--password", icloud_pass]
    result = subprocess.run(cmd)
    if result.returncode == 0:
        click.echo("\nSession saved — no 2FA needed for subsequent runs.")
    else:
        click.echo("\nAuth failed. Check credentials and try again.", err=True)


@cli.command()
@click.option("--icloud-user", envvar="ICLOUD_USERNAME", required=True, help="Apple ID email")
@click.option("--icloud-pass", envvar="ICLOUD_PASSWORD", default=None)
@click.option("--days", default=15, show_default=True, help="How many days back in iCloud to preview")
def catalog(icloud_user, icloud_pass, days):
    """Phase 1 (optional): Preview which iCloud assets will be downloaded."""
    from photo_tribute.phases.audit import run_catalog
    run_catalog(icloud_user, icloud_pass, days=days)


@cli.command()
@click.option("--icloud-user", envvar="ICLOUD_USERNAME", required=True)
@click.option("--icloud-pass", envvar="ICLOUD_PASSWORD", default=None)
@click.option("--days", default=15, show_default=True, help="How many days back to download")
def download(icloud_user, icloud_pass, days):
    """Phase 2a: Download assets from iCloud into ./staging/ and record EXIF dates."""
    from photo_tribute.phases.download import run_download
    run_download(icloud_user, icloud_pass, days=days)


@cli.command()
def fix():
    """Phase 2b: Verify and correct EXIF dates in staged files using exiftool."""
    from photo_tribute.phases.fix import run_fix
    run_fix()


@cli.command()
def swap():
    """Phase 3: Upload corrected files to Google Photos."""
    from photo_tribute.google_auth import get_credentials
    from photo_tribute.phases.swap import run_swap
    click.echo("Authenticating with Google Photos...")
    creds = get_credentials()
    run_swap(creds)


@cli.command()
def status():
    """Show a summary of the current state.json."""
    state = State.load()
    if not state.assets:
        click.echo("No state found. Run `photo-tribute download` first.")
        return
    summary = state.summary()
    total = sum(summary.values())
    click.echo(f"\nTotal assets tracked: {total}")
    for status_val, count in sorted(summary.items()):
        click.echo(f"  {status_val:<14} {count}")


@cli.command()
@click.option("--icloud-user", envvar="ICLOUD_USERNAME", required=True)
@click.option("--icloud-pass", envvar="ICLOUD_PASSWORD", default=None)
@click.option("--days", default=15, show_default=True)
def run_all(icloud_user, icloud_pass, days):
    """Run all phases: download → fix → swap."""
    from photo_tribute.google_auth import get_credentials
    from photo_tribute.phases.download import run_download
    from photo_tribute.phases.fix import run_fix
    from photo_tribute.phases.swap import run_swap

    click.echo("=== Phase 1: Download (iCloud) ===")
    run_download(icloud_user, icloud_pass, days=days)

    click.echo("\n=== Phase 2: Fix EXIF ===")
    run_fix()

    click.echo("\n=== Phase 3: Upload (Google Photos) ===")
    creds = get_credentials()
    run_swap(creds)

    click.echo("\n=== Done ===")
    ctx = click.get_current_context()
    ctx.invoke(status)
