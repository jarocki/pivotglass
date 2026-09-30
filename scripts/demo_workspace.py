#!/usr/bin/env python3
"""Run an isolated offline Pivotglass workspace for documentation/demo capture."""
from __future__ import annotations

import argparse
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import mkdtemp

from pivotglass.agent.tools import ToolContext
from pivotglass.web.server import WebCockpitService, _handler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8770)
    args = parser.parse_args()
    root = Path(mkdtemp(prefix='pivotglass-demo-'))
    service = WebCockpitService(ToolContext(config_dir=root / 'config', workspace_dir=root / 'workspaces'))
    receipt = service.execute_command('workspace learn release-tour')
    if receipt.get('error'):
        raise RuntimeError(receipt['error'])
    static = Path(__file__).resolve().parents[1] / 'web' / 'out'
    server = ThreadingHTTPServer(('127.0.0.1', args.port), _handler(service, static))
    print(f'Synthetic demo root: {root}\nLoopback URL: http://127.0.0.1:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
