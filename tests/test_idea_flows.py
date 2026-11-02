import concurrent.futures
import contextlib
import http.server
import importlib.util
import json
import os
from pathlib import Path
import shlex
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/idea_flows.py'
spec = importlib.util.spec_from_file_location('idea_flows', SCRIPT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='idea flows ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / 'config.json'
        self.data = self.root / 'data with spaces'
        self.project = self.root / 'project with spaces'
        self.project.mkdir()
        m.private_write(self.config, {'projects': [{'id': 'sample', 'name': 'Sample', 'cwd': str(self.project)}]})
        self.t = m.Tracker(self.config, self.data)

    def event(self, name='UserPromptSubmit', turn='turn', prompt='Please build it', **extra):
        return dict(hook_event_name=name, cwd=str(self.project), session_id='session', turn_id=turn, prompt=prompt, **extra)

    def record(self, status='dev', turn='turn', **extra):
        args = m.parser().parse_args(['record', '--session', 'session', '--turn', turn, '--status', status, '--progress', 'Implemented a feature', '--evidence', 'Changed source files'])
        for key, value in extra.items():
            setattr(args, key, value)
        return self.t.record(args)

    def rows(self, table):
        with self.t.db() as db:
            return [json.loads(row[0]) for row in db.execute('SELECT payload FROM ' + table)]

    def test_database_connection_closes_after_transaction(self):
        with self.t.db() as db:
            db.execute("SELECT 1")
        with self.assertRaises(sqlite3.ProgrammingError):
            db.execute("SELECT 1")

    def test_unenrolled_project_does_nothing(self):
        event = self.event()
        event['cwd'] = str(self.root)
        self.assertEqual(self.t.hook(event), {})
        self.assertFalse(self.data.exists())

    def test_most_specific_directory_wins(self):
        nested = self.project / 'child'
        config = {'projects': self.t.config['projects'] + [{'id': 'child', 'cwd': str(nested)}]}
        self.assertEqual(m.project_at(config, nested / 'more')['id'], 'child')

    def test_record_command_executes_with_spaces_and_explicit_paths(self):
        event = self.event()
        self.t.hook(event)
        command = self.t.command(event)
        if os.name == 'nt':
            result = subprocess.run(command + ' --status dev --progress implemented', shell=False, capture_output=True, text=True)
        else:
            result = subprocess.run(shlex.split(command) + ['--status', 'dev', '--progress', 'implemented'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.t.hook(self.event('Stop'))
        self.assertEqual(self.rows('projects')[0]['status'], 'dev')

    def test_archive_requires_current_user_quote(self):
        self.t.hook(self.event(prompt='Archive this project please'))
        with self.assertRaises(ValueError):
            self.record('discarded', archive_evidence='old instruction')
        self.record('discarded', archive_evidence='Archive this project')
        self.t.hook(self.event('Stop'))
        self.assertTrue(self.rows('events')[0]['archiveConfirmed'])

    def test_live_requires_verified_url(self):
        self.t.hook(self.event())
        with self.assertRaises(ValueError):
            self.record('live')
        with self.assertRaises(ValueError):
            self.record('live', deployment_verified=True, deployment_url='file:///tmp/build')
        self.record('live', deployment_verified=True, deployment_url='https://example.com')
        self.t.hook(self.event('Stop'))
        self.t.hook(self.event(turn='next'))
        self.record('live', turn='next')
        self.t.hook(self.event('Stop', turn='next'))
        self.assertEqual(self.rows('projects')[0]['deploymentUrl'], 'https://example.com')

    def test_missing_record_continues_once(self):
        self.t.hook(self.event())
        self.assertEqual(self.t.hook(self.event('Stop'))['decision'], 'block')
        self.assertNotIn('decision', self.t.hook(self.event('Stop', stop_hook_active=True)))
        self.assertEqual(self.rows('contexts'), [])
        self.assertEqual(self.rows('projects'), [])

    def test_continuation_can_be_disabled(self):
        self.t.config['require_record'] = False
        self.t.hook(self.event())
        self.assertNotIn('decision', self.t.hook(self.event('Stop')))

    def test_stop_is_idempotent_and_deletes_prompt(self):
        self.t.hook(self.event(prompt='PRIVATE ORIGINAL PROMPT'))
        self.record()
        self.t.hook(self.event('Stop'))
        self.t.hook(self.event('Stop'))
        self.assertEqual(len(self.rows('events')), 1)
        self.assertEqual(self.rows('contexts'), [])
        self.assertNotIn('PRIVATE ORIGINAL PROMPT', json.dumps(self.rows('events')))

    def test_concurrent_turns_and_late_stop(self):
        def run(index):
            turn = str(index)
            tracker = m.Tracker(self.config, self.data)
            tracker.hook(self.event(turn=turn))
            args = m.parser().parse_args(['record', '--session', 'session', '--turn', turn, '--status', 'dev', '--progress', turn])
            tracker.record(args)
            tracker.hook(self.event('Stop', turn=turn))
        # Bootstrap schema before exercising independent connections.
        with self.t.db():
            pass
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(run, range(12)))
        events = self.rows('events')
        self.assertEqual(len(events), 12)
        self.assertEqual(self.rows('projects')[0]['observedAt'], max(p['observedAt'] for p in events))

    @contextlib.contextmanager
    def receiver(self, redirect=False):
        received = []
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                received.append((self.path, body, self.headers.get('Authorization')))
                self.send_response(302 if redirect else 204)
                if redirect:
                    self.send_header('Location', '/should-not-follow')
                self.end_headers()
            def log_message(self, *args):
                pass
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield 'http://127.0.0.1:%s/sync' % server.server_port, received
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_failed_delivery_retries_with_environment_auth(self):
        self.t.hook(self.event())
        self.record()
        self.t.config['webhook'] = {'url': 'http://127.0.0.1:1/sync'}
        self.assertIn('pending', self.t.hook(self.event('Stop'))['systemMessage'])
        with self.receiver() as (url, received), patch.dict(os.environ, {'TEST_IDEA_TOKEN': 'test-only-credential'}):
            self.t.config['webhook'] = {'url': url, 'headers_env': {'Authorization': 'TEST_IDEA_TOKEN'}}
            self.assertEqual(self.t.flush(), 1)
            self.assertEqual(self.t.flush(), 0)
            self.assertEqual(received[0][2], 'test-only-credential')
        self.assertNotIn('test-only-credential', json.dumps(self.rows('events')))

    def test_redirect_is_not_followed(self):
        self.t.hook(self.event())
        self.record()
        self.t.hook(self.event('Stop'))
        with self.receiver(redirect=True) as (url, received):
            self.t.config['webhook'] = {'url': url}
            with self.assertRaises(Exception):
                self.t.flush()
            self.assertEqual(len(received), 1)
        with self.t.db() as db:
            self.assertEqual(db.execute('SELECT delivered FROM events').fetchone()[0], 0)

    def test_unsafe_webhook_urls_rejected(self):
        for url in ('http://example.com', 'https://user:pass@example.com', 'https://example.com/#secret'):
            with self.assertRaises(ValueError):
                m.check_url(url)

    def test_cli_init_enroll_and_private_permissions(self):
        config = self.root / 'cli.json'
        base = [sys.executable, str(SCRIPT), '--config', str(config), '--data-dir', str(self.data)]
        subprocess.run(base + ['init'], check=True, capture_output=True)
        subprocess.run(base + ['enroll', '--id', 'cli', '--name', 'CLI', '--cwd', str(self.project)], check=True, capture_output=True)
        subprocess.run(base + ['init'], check=True, capture_output=True)
        self.assertEqual(json.loads(config.read_text())['projects'][0]['id'], 'cli')
        if os.name != 'nt':
            self.assertEqual(config.stat().st_mode & 0o777, 0o600)

    def test_bad_hook_config_still_outputs_json(self):
        self.config.write_text('{invalid')
        result = subprocess.run([sys.executable, str(SCRIPT), '--config', str(self.config), 'hook'], input='{}', text=True, capture_output=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn('systemMessage', json.loads(result.stdout))


if __name__ == '__main__':
    unittest.main()
