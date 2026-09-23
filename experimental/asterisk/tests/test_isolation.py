"""Process-isolated checks: optional telephony cannot become a core dependency."""
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def run_isolated(source, enabled=None):
    environment = os.environ.copy()
    for key in tuple(environment):
        if key.startswith('TELEPHONY_'):
            environment.pop(key)
    if enabled is not None:
        environment['TELEPHONY_ENABLED'] = enabled
    environment['PYTHONPATH'] = os.pathsep.join((str(PROJECT_ROOT / 'backend'), str(PROJECT_ROOT)))
    environment['PYTHONIOENCODING'] = 'utf-8'
    environment['PYTHONDONTWRITEBYTECODE'] = '1'
    environment['CALLAI_MODEL'] = 'gpt-6-astra'
    result = subprocess.run([sys.executable, '-c', textwrap.dedent(source)],
                            cwd=PROJECT_ROOT, env=environment, capture_output=True,
                            encoding='utf-8', timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout + result.stderr


@pytest.mark.parametrize('enabled', [None, 'false', 'true'])
@pytest.mark.parametrize('failure', ['ModuleNotFoundError', 'RuntimeError'])
def test_core_starts_and_serves_when_telephony_is_absent_or_crashing(enabled, failure):
    # A fresh interpreter catches even accidental import-time coupling. The
    # optional package is deliberately unavailable, including when enabled.
    script = '''
        import asyncio
        import gc
        import importlib.abc
        from pathlib import Path
        import sys
        import tempfile
        import httpx

        class UnavailableTelephony(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname == 'experimental' or fullname.startswith('experimental.'):
                    raise FAILURE('Fixture: telephony must not be imported by the core')

        sys.meta_path.insert(0, UnavailableTelephony())
        from app.config.settings import Settings
        from app.main import create_app

        def unexpected_network(request):
            raise AssertionError('Core startup/health unexpectedly used an external service')

        async def check():
            with tempfile.TemporaryDirectory() as directory:
                app = create_app(Settings(api_key='isolation-fixture'),
                                 httpx.MockTransport(unexpected_network),
                                 database_path=Path(directory) / 'state.sqlite')
                async with app.router.lifespan_context(app):
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app),
                                                 base_url='http://isolated') as client:
                        assert (await client.get('/health')).json()['status'] == 'ok'
                        session = (await client.post('/api/session', json={'language': 'kk'})).json()
                        saved = await client.get('/api/session/' + session['conversation_id'])
                        assert saved.status_code == 200 and saved.json()['response_language'] == 'kk'
                        assert (await client.get('/api/supervisor/events')).status_code == 200
                        assert (await client.get('/api/voice/status')).status_code == 200
                # SQLite connection context managers commit but do not close;
                # collect their cycles before Windows removes this temp dir.
                gc.collect()
            assert not any(name == 'experimental' or name.startswith('experimental.') for name in sys.modules)

        asyncio.run(check())
        print('Core independent: PASS')
    '''.replace('FAILURE(', failure + '(')
    assert 'Core independent: PASS' in run_isolated(script, enabled)


@pytest.mark.parametrize('enabled', [None, 'false', '0'])
def test_disabled_entrypoint_imports_no_runtime_and_opens_no_network(enabled):
    output = run_isolated('''
        import importlib.abc
        import socket
        import sys

        attempts = []
        forbidden = ('experimental.asterisk.run', 'httpx', 'aiohttp', 'websockets', 'app')
        class RuntimeForbidden(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if any(fullname == name or fullname.startswith(name + '.') for name in forbidden):
                    attempts.append(fullname)
                    raise AssertionError('Disabled entrypoint imported a runtime dependency')
        sys.meta_path.insert(0, RuntimeForbidden())
        def no_network(*args, **kwargs):
            attempts.append('network')
            raise AssertionError('Disabled entrypoint opened network transport')
        socket.create_connection = no_network
        socket.socket.connect = no_network
        socket.socket.connect_ex = no_network
        socket.socket.bind = no_network

        from experimental.asterisk.__main__ import main
        assert main() == 0
        assert attempts == []
        assert not any(name == 'experimental.asterisk.run' or name.startswith('app.') for name in sys.modules)
        print('Disabled entrypoint isolated: PASS')
    ''', enabled)
    assert 'Disabled entrypoint isolated: PASS' in output


@pytest.mark.parametrize('failure', ['ModuleNotFoundError', 'RuntimeError'])
def test_enabled_entrypoint_contains_optional_runtime_import_failure(failure):
    script = '''
        import importlib.abc
        import sys
        attempted = []
        class BrokenRuntime(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname == 'experimental.asterisk.run':
                    attempted.append(fullname)
                    raise FAILURE('Fixture runtime unavailable')
        sys.meta_path.insert(0, BrokenRuntime())
        from experimental.asterisk.__main__ import main
        assert main() == 0
        assert attempted == ['experimental.asterisk.run']
        assert not any(name == 'app' or name.startswith('app.') for name in sys.modules)
        print('Optional runtime failure contained: PASS')
    '''.replace('FAILURE(', failure + '(')
    assert 'Optional runtime failure contained: PASS' in run_isolated(script, 'true')


def test_enabled_unreachable_runtime_failure_is_contained_without_importing_core():
    # The connection failure is injected; no PBX, socket or HTTP call is made.
    output = run_isolated('''
        import sys
        import types
        runtime = types.ModuleType('experimental.asterisk.run')
        calls = []
        async def fail_to_connect(config):
            calls.append(config)
            raise ConnectionRefusedError('Fixture: optional Asterisk unreachable')
        runtime.run = fail_to_connect
        sys.modules[runtime.__name__] = runtime
        from experimental.asterisk.__main__ import main
        assert main() == 0
        assert len(calls) == 1
        assert not any(name == 'app' or name.startswith('app.') for name in sys.modules)
        print('Unreachable telephony contained: PASS')
    ''', 'true')
    assert 'Unreachable telephony contained: PASS' in output


def test_enabled_bad_configuration_does_not_start_runtime():
    output = run_isolated('''
        import sys
        import types
        from experimental.asterisk.config import TelephonyConfig
        calls = []
        def invalid_config(*args, **kwargs):
            raise ValueError('Fixture: invalid optional configuration')
        TelephonyConfig.from_env = invalid_config
        runtime = types.ModuleType('experimental.asterisk.run')
        async def unexpected_run(config):
            calls.append(config)
            raise AssertionError('Invalid optional configuration started a runtime')
        runtime.run = unexpected_run
        sys.modules[runtime.__name__] = runtime
        from experimental.asterisk.__main__ import main
        assert main() == 0 and calls == []
        print('Bad optional configuration contained: PASS')
    ''', 'true')
    assert 'Bad optional configuration contained: PASS' in output
