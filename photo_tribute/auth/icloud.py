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
        print("Two-factor authentication required.")
        print("Check your trusted device for a verification code.")
        code = input("Enter 2FA code: ").strip()
        result = api.validate_2fa_code(code)
        if not result:
            raise RuntimeError("2FA validation failed.")
        if not api.is_trusted_session:
            api.trust_session()

    elif api.requires_2sa:
        # Older two-step verification
        devices = api.trusted_devices
        for i, dev in enumerate(devices):
            print(f"  [{i}] {dev.get('deviceName', 'Unknown')}")
        idx = int(input("Select device: "))
        device = devices[idx]
        if not api.send_verification_code(device):
            raise RuntimeError("Failed to send verification code.")
        code = input("Verification code: ").strip()
        if not api.validate_verification_code(device, code):
            raise RuntimeError("Verification code validation failed.")

    return api
