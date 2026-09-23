"""Explicit opt-in launcher: python -m experimental.asterisk.

The web backend does not import this module and does not launch this process.
"""
import asyncio
import logging
from .config import TelephonyConfig, is_enabled


def main() -> int:
    logging.basicConfig(level=logging.INFO, format='[TELEPHONY] %(message)s')
    if not is_enabled():
        logging.info('disabled')
        return 0
    try:
        from .run import run  # Optional runtime/dependencies loaded only here.
        asyncio.run(run(TelephonyConfig.from_env()))
    except KeyboardInterrupt:
        logging.info('stopped')
    except Exception as exc:
        # No exception text: provider URLs or credentials must not leak to logs.
        logging.warning('unavailable — disabled (%s)', type(exc).__name__)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
