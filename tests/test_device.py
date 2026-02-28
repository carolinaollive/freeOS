"""Tests for the device management module."""

import os
import subprocess
from unittest import mock

import pytest

from android_sms_to_iphone.device import (
    DeviceError,
    _run,
    check_tools,
    get_device_info,
    list_devices,
)


# We can't test actual device interaction in CI, so we mock subprocess calls.


class TestCheckTools:
    def test_all_tools_present(self):
        with mock.patch("shutil.which", return_value="/usr/local/bin/tool"):
            assert check_tools() is True

    def test_missing_tools(self):
        def fake_which(name):
            if name == "idevicebackup2":
                return None
            return "/usr/local/bin/" + name

        with mock.patch("shutil.which", side_effect=fake_which):
            with pytest.raises(DeviceError, match="Missing tools"):
                check_tools()


class TestListDevices:
    def test_no_devices(self):
        result = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr=""
        )
        with mock.patch("android_sms_to_iphone.device._run", return_value=result):
            assert list_devices() == []

    def test_one_device(self):
        result = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout="abcdef1234567890abcdef1234567890abcdef12\n",
            stderr="",
        )
        with mock.patch("android_sms_to_iphone.device._run", return_value=result):
            devices = list_devices()
            assert len(devices) == 1
            assert devices[0] == "abcdef1234567890abcdef1234567890abcdef12"

    def test_multiple_devices(self):
        result = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout="udid1\nudid2\n",
            stderr="",
        )
        with mock.patch("android_sms_to_iphone.device._run", return_value=result):
            devices = list_devices()
            assert len(devices) == 2


class TestGetDeviceInfo:
    def test_parses_info(self):
        result = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout="DeviceName: My iPhone\nProductType: iPhone14,5\nProductVersion: 17.2\n",
            stderr="",
        )
        with mock.patch("android_sms_to_iphone.device._run", return_value=result):
            info = get_device_info()
            assert info["DeviceName"] == "My iPhone"
            assert info["ProductType"] == "iPhone14,5"
            assert info["ProductVersion"] == "17.2"

    def test_device_not_found(self):
        result = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="No device found"
        )
        with mock.patch("android_sms_to_iphone.device._run", return_value=result):
            with pytest.raises(DeviceError, match="Could not read device info"):
                get_device_info()


class TestRun:
    def test_command_not_found(self):
        with pytest.raises(DeviceError, match="Command not found"):
            _run(["nonexistent_command_12345"])
