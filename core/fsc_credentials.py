"""Resolve local API credentials without saving or printing their value."""
from __future__ import annotations
import os
from pathlib import Path


def law_api_key() -> str:
    for name in ('LAW_API_KEY', 'LAW_OC'):
        if os.environ.get(name, '').strip():
            return os.environ[name].strip()
    from dotenv import dotenv_values
    values = dotenv_values(Path(__file__).resolve().parents[1] / '.env')
    for name in ('LAW_API_KEY', 'LAW_OC'):
        if (values.get(name) or '').strip():
            return values[name].strip()
    if os.name == 'nt':
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment') as registry:
                for name in ('LAW_API_KEY', 'LAW_OC'):
                    try:
                        value, _ = winreg.QueryValueEx(registry, name)
                        if value.strip():
                            return value.strip()
                    except FileNotFoundError:
                        pass
        except FileNotFoundError:
            pass
    return ''
