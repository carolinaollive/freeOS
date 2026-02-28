"""Manage iPhone connections via libimobiledevice CLI tools.

Automates the full backup → modify → restore cycle so the user
only needs to plug in their iPhone and run one command.

Required external tools (from libimobiledevice):
  idevice_id       - list connected device UDIDs
  ideviceinfo      - get device information
  idevicepair      - pair/validate trust with device
  idevicebackup2   - create and restore backups

Install:
  macOS:  brew install libimobiledevice
  Linux:  sudo apt install libimobiledevice-utils
"""

import logging
import os
import shutil
import subprocess
import sys
import time

logger = logging.getLogger(__name__)


class DeviceError(Exception):
    """Raised when device operations fail."""


def _run(cmd: list[str], check: bool = True,
         timeout: int = 600) -> subprocess.CompletedProcess:
    """Run a shell command and return the result."""
    logger.debug("Running: %s", " ".join(cmd))
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
        )
        if check and result.returncode != 0:
            logger.debug("stdout: %s", result.stdout)
            logger.debug("stderr: %s", result.stderr)
        return result
    except FileNotFoundError:
        raise DeviceError(
            f"Command not found: {cmd[0]}\n\n"
            "You need to install libimobiledevice:\n"
            "  macOS:  brew install libimobiledevice\n"
            "  Linux:  sudo apt install libimobiledevice-utils\n"
        )
    except subprocess.TimeoutExpired:
        raise DeviceError(f"Command timed out after {timeout}s: {' '.join(cmd)}")


def check_tools() -> bool:
    """Check that required libimobiledevice tools are installed."""
    tools = ["idevice_id", "ideviceinfo", "idevicebackup2"]
    missing = []
    for tool in tools:
        if shutil.which(tool) is None:
            missing.append(tool)

    if missing:
        raise DeviceError(
            f"Missing tools: {', '.join(missing)}\n\n"
            "Install libimobiledevice:\n"
            "  macOS:  brew install libimobiledevice\n"
            "  Linux:  sudo apt install libimobiledevice-utils\n"
        )
    return True


def list_devices() -> list[str]:
    """Return a list of connected device UDIDs."""
    result = _run(["idevice_id", "-l"], check=False)
    if result.returncode != 0:
        return []
    udids = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return udids


def get_device_info(udid: str = "") -> dict[str, str]:
    """Get device information as a dict."""
    cmd = ["ideviceinfo"]
    if udid:
        cmd.extend(["-u", udid])

    result = _run(cmd, check=False)
    if result.returncode != 0:
        raise DeviceError(
            "Could not read device info. Make sure your iPhone is:\n"
            "  1. Connected via USB\n"
            "  2. Unlocked\n"
            "  3. Trusting this computer (tap 'Trust' if prompted)\n"
        )

    info = {}
    for line in result.stdout.splitlines():
        if ": " in line:
            key, _, value = line.partition(": ")
            info[key.strip()] = value.strip()
    return info


def get_device_name(udid: str = "") -> str:
    """Get a human-readable device name."""
    info = get_device_info(udid)
    name = info.get("DeviceName", "iPhone")
    product = info.get("ProductType", "")
    ios_ver = info.get("ProductVersion", "")
    parts = [name]
    if product:
        parts.append(f"({product})")
    if ios_ver:
        parts.append(f"iOS {ios_ver}")
    return " ".join(parts)


def ensure_paired(udid: str = ""):
    """Make sure the device is paired (trusted) with this computer."""
    cmd = ["idevicepair"]
    if udid:
        cmd.extend(["-u", udid])
    cmd.append("validate")

    result = _run(cmd, check=False)
    if result.returncode != 0:
        # Try to pair
        pair_cmd = ["idevicepair"]
        if udid:
            pair_cmd.extend(["-u", udid])
        pair_cmd.append("pair")

        print("Please unlock your iPhone and tap 'Trust' if prompted...")
        pair_result = _run(pair_cmd, check=False, timeout=60)
        if pair_result.returncode != 0:
            raise DeviceError(
                "Could not pair with device. Please:\n"
                "  1. Unlock your iPhone\n"
                "  2. Tap 'Trust' when prompted\n"
                "  3. Try again\n"
            )
    logger.info("Device paired and trusted")


def create_backup(backup_dir: str, udid: str = "") -> str:
    """Create an unencrypted backup of the iPhone.

    Returns the path to the backup directory.
    """
    os.makedirs(backup_dir, exist_ok=True)

    cmd = ["idevicebackup2"]
    if udid:
        cmd.extend(["-u", udid])
    cmd.extend(["backup", "--full", backup_dir])

    print("Creating iPhone backup (this may take several minutes)...")
    logger.info("Running backup to: %s", backup_dir)

    # Run backup with a long timeout (can take 30+ minutes for large phones)
    result = _run(cmd, check=False, timeout=7200)

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "encryption" in stderr.lower() or "password" in stderr.lower():
            raise DeviceError(
                "Your iPhone has backup encryption enabled.\n"
                "To disable it: Settings > General > Transfer or Reset > "
                "Reset All Settings\n"
                "Or: Connect in Finder and uncheck 'Encrypt local backup'\n"
                "Then try again."
            )
        raise DeviceError(f"Backup failed: {stderr or result.stdout}")

    # Find the actual backup subdirectory (named by device UDID)
    if udid:
        actual_dir = os.path.join(backup_dir, udid)
    else:
        # Find the newest subdirectory
        subdirs = [
            os.path.join(backup_dir, d) for d in os.listdir(backup_dir)
            if os.path.isdir(os.path.join(backup_dir, d))
        ]
        if not subdirs:
            raise DeviceError("Backup completed but no backup directory was created")
        actual_dir = max(subdirs, key=os.path.getmtime)

    if not os.path.isfile(os.path.join(actual_dir, "Manifest.db")):
        raise DeviceError(
            f"Backup directory exists but looks incomplete: {actual_dir}"
        )

    print("Backup complete!")
    logger.info("Backup created at: %s", actual_dir)
    return actual_dir


def restore_backup(backup_dir: str, udid: str = ""):
    """Restore a backup to the iPhone.

    backup_dir should be the PARENT directory containing the UDID-named
    backup folder (idevicebackup2 expects this layout).
    """
    # idevicebackup2 restore expects the parent dir, not the backup itself
    parent_dir = os.path.dirname(backup_dir)

    cmd = ["idevicebackup2"]
    if udid:
        cmd.extend(["-u", udid])
    # --system  = restore system files
    # --settings = restore settings
    # We do NOT use --reboot to let the user control when to reboot
    cmd.extend(["restore", "--system", "--settings", parent_dir])

    print("Restoring backup to iPhone (this may take several minutes)...")
    logger.info("Restoring backup from: %s", parent_dir)

    result = _run(cmd, check=False, timeout=7200)

    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise DeviceError(
            f"Restore failed: {stderr or result.stdout}\n\n"
            "If the restore fails, your iPhone data is still safe - "
            "the original data hasn't been modified."
        )

    print("Restore complete! Your iPhone may restart.")
    logger.info("Restore completed successfully")


def wait_for_device(timeout: int = 60) -> str:
    """Wait for an iPhone to be connected. Returns the UDID."""
    print("Waiting for iPhone to be connected...")
    start = time.time()
    while time.time() - start < timeout:
        devices = list_devices()
        if devices:
            udid = devices[0]
            logger.info("Found device: %s", udid)
            return udid
        time.sleep(2)

    raise DeviceError(
        "No iPhone detected. Make sure your iPhone is:\n"
        "  1. Connected via USB cable\n"
        "  2. Unlocked\n"
        "  3. Trusting this computer\n"
    )
