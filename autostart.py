import os
import winreg

def enable_autostart():

    exe = os.path.abspath("RadiologyQueue.exe")

    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0,
        winreg.KEY_SET_VALUE
    )

    winreg.SetValueEx(
        key,
        "RadiologyQueue",
        0,
        winreg.REG_SZ,
        exe
    )