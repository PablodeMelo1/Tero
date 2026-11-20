"""Exercise deployment success and rollback without a real deployment host."""
import http.server
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Handler(http.server.BaseHTTPRequestHandler):
    healthy = True

    def do_GET(self):
        if self.path == '/health':
            self.send_response(200 if self.healthy else 503)
            self.end_headers()
            self.wfile.write(b'OK')
        elif self.path.startswith('/api/checkout/'):
            self.send_response(404)
            self.end_headers()
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'[]')

    def log_message(self, *_args):
        pass


class DeploymentTests(unittest.TestCase):
    def test_success_advances_current_and_failure_restores_previous(self):
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.addCleanup(setattr, Handler, 'healthy', True)
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            root = temp / 'host'
            root.mkdir()
            (root / '.env').write_text('')
            release = temp / 'release'
            release.mkdir()
            shutil.copytree(ROOT / 'scripts', release / 'scripts')
            shutil.copytree(ROOT / 'deploy', release / 'deploy')
            sha = 'a' * 40
            manifest = {'commit': sha, 'images': {s: f'docker.io/test/tero-{s}@sha256:' + 'b' * 64
                        for s in ('ui', 'admin', 'catalog', 'cart', 'checkout', 'orders')}}
            (release / 'manifest.json').write_text(json.dumps(manifest))
            binary = temp / 'bin'
            binary.mkdir()
            docker = binary / 'docker'
            docker.write_text('#!/usr/bin/env python3\nimport os,sys\n'
                              'with open(os.environ["DOCKER_TEST_LOG"], "a") as log: log.write(" ".join(sys.argv[1:])+"\\n")\n'
                              'if "port" in sys.argv: print("127.0.0.1:"+os.environ["DOCKER_TEST_PORT"])\n')
            docker.chmod(0o755)
            env = dict(os.environ, PATH=str(binary) + ':' + os.environ['PATH'], RELEASE_SHA=sha,
                       DOCKER_TEST_PORT=str(server.server_port), DOCKER_TEST_LOG=str(temp / 'docker.log'))
            command = ['bash', 'scripts/deploy.sh', 'dev', str(root)]
            result = subprocess.run(command, cwd=release, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual((root / 'current').resolve(), release)
            self.assertEqual((root / 'deployed-commit').read_text().strip(), sha)
            second = temp / 'second'
            shutil.copytree(release, second)
            Handler.healthy = False
            result = subprocess.run(command, cwd=second, env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('restoring previous images', result.stderr)
            self.assertEqual((root / 'current').resolve(), release)
            calls = (temp / 'docker.log').read_text().splitlines()
            self.assertTrue(any(str(release / 'images.env') in c and 'up -d --no-build --wait' in c for c in calls[-3:]))


if __name__ == '__main__':
    unittest.main()
