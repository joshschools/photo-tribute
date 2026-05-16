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
    """Authenticate with iCloud and save session cookie (do this once, lasts ~2 months)."""
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
        click.echo("\nSession saved to .icloud-session/ — no 2FA needed for subsequent runs.")
    else:
        click.echo("\nAuth failed. Check your credentials and try again.", err=True)


@cli.command()
@click.option("--icloud-user", envvar="ICLOUD_USERNAME", required=True, help="Apple ID email")
@click.option("--icloud-pass", envvar="ICLOUD_PASSWORD", default=None, help="Apple ID password (or set ICLOUD_PASSWORD)")
@click.option("--days", default=10, show_default=True, help="How many days back in iCloud to catalog")
def catalog(icloud_user, icloud_pass, days):
    """Phase 1: Catalog iCloud assets from the migration window into state.json."""
    from photo_tribute.auth.icloud import get_session
    from photo_tribute.phases.audit import run_catalog

    click.echo("Authenticating with iCloud...")
    icloud_api = get_session(icloud_user, icloud_pass)
    run_catalog(icloud_api, days=days)


@cli.command()
@click.option("--icloud-user", envvar="ICLOUD_USERNAME", required=True)
@click.option("--icloud-pass", envvar="ICLOUD_PASSWORD", default=None)
def download(icloud_user, icloud_pass):
    """Phase 2a: Download catalogued assets from iCloud into ./staging/."""
    from photo_tribute.phases.download import run_download
    run_download(icloud_user, icloud_pass)


@cli.command()
def fix():
    """Phase 2b: Verify and correct EXIF dates in staged files using exiftool."""
    from photo_tribute.phases.fix import run_fix
    run_fix()


@cli.command()
def swap():
    """Phase 3: Upload corrected files to Google Photos."""
    from photo_tribute.auth.google import get_credentials
    from photo_tribute.phases.swap import run_swap

    click.echo("Authenticating with Google Photos...")
    creds = get_credentials()
    run_swap(creds)


@cli.command()
def status():
    """Show a summary of the current state.json."""
    state = State.load()
    if not state.assets:
        click.echo("No state found. Run `photo-tribute catalog` first.")
        return

    summary = state.summary()
    total = sum(summary.values())
    click.echo(f"\nTotal assets tracked: {total}")
    for status_val, count in sorted(summary.items()):
        click.echo(f"  {status_val:<14} {count}")


@cli.command()
@click.option("--icloud-user", envvar="ICLOUD_USERNAME", required=True)
@click.option("--icloud-pass", envvar="ICLOUD_PASSWORD", default=None)
@click.option("--days", default=10, show_default=True)
def run_all(icloud_user, icloud_pass, days):
    """Run all phases in sequence: catalog → download → fix → swap."""
    from photo_tribute.auth.icloud import get_session
    from photo_tribute.auth.google import get_credentials
    from photo_tribute.phases.audit import run_catalog
    from photo_tribute.phases.download import run_download
    from photo_tribute.phases.fix import run_fix
    from photo_tribute.phases.swap import run_swap

    click.echo("=== Phase 1: Catalog (iCloud) ===")
    icloud_api = get_session(icloud_user, icloud_pass)
    run_catalog(icloud_api, days=days)

    click.echo("\n=== Phase 2a: Download ===")
    run_download(icloud_user, icloud_pass)

    click.echo("\n=== Phase 2b: Fix EXIF ===")
    run_fix()

    click.echo("\n=== Phase 3: Upload ===")
    creds = get_credentials()
    run_swap(creds)

    click.echo("\n=== Done ===")
    ctx = click.get_current_context()
    ctx.invoke(status)
