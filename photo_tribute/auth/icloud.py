"""iCloud authentication via pyicloud-ipd with session persistence."""

import os
from pathlib import Path
from typing import Optional

SESSION_DIR = Path(".icloud-session")


def get_session(username: str, password: Optional[str] = None):
    """Return an authenticated PyiCloudService, prompting for 2FA if needed."""
    from pyicloud_ipd import PyiCloudService

    SESSION_DIR.mkdir(exist_ok=True)
    cookie_dir = str(SESSION_DIR)

    pw = password or os.environ.get("ICLOUD_PASSWORD")
    if not pw:
        import getpass
        pw = getpass.getpass(f"iCloud password for {username}: ")

    api = PyiCloudService(username, pw, cookie_directory=cookie_dir)

    if api.requires_2fa:
        _handle_2fa(api)
    elif api.requires_2sa:
        _handle_2sa(api)

    return api


def _handle_2fa(api) -> None:
    """Handle modern two-factor authentication.

    Apple's current iOS flow shows an 'Are you trying to sign in?' prompt on
    trusted devices. Tapping Allow may directly approve the session (no code),
    or may display a 6-digit code depending on the iOS version and account
    security settings.
    """
    print("\nTwo-factor authentication required.")
    print("A notification has been sent to your trusted Apple device.")
    print()
    response = input(
        "Tap Allow on your device, then:\n"
        "  - Press Enter if no code appeared (device approval)\n"
        "  - Or type the 6-digit code and press Enter: "
    ).strip()

    if response == "":
        # Device tapped Allow — session may already be approved
        if not api.is_trusted_session:
            api.trust_session()
        if not api.is_trusted_session:
            # Some accounts still require a code even after device approval
            code = input("Session not yet trusted. Enter the 6-digit code from your device: ").strip()
            if not api.validate_2fa_code(code):
                raise RuntimeError("2FA validation failed.")
    else:
        # User entered a 6-digit code
        if not api.validate_2fa_code(response):
            raise RuntimeError("2FA validation failed.")
        if not api.is_trusted_session:
            api.trust_session()


def _handle_2sa(api) -> None:
    """Handle older two-step verification."""
    devices = api.trusted_devices
    print("\nTwo-step verification required. Select a device:")
    for i, dev in enumerate(devices):
        print(f"  [{i}] {dev.get('deviceName', 'Unknown')}")
    idx = int(input("Device number: "))
    device = devices[idx]
    if not api.send_verification_code(device):
        raise RuntimeError("Failed to send verification code.")
    code = input("Verification code: ").strip()
    if not api.validate_verification_code(device, code):
        raise RuntimeError("Verification code validation failed.")
