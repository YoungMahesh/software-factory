"""T3 Code container setup and pairing utilities."""

from __future__ import annotations

import json
import logging
import time

import modal

from sandbox.cli import generate_ascii_qr

logger = logging.getLogger(__name__)


def setup_t3(
    sandbox: modal.Sandbox,
    t3_url: str,
    ssh_host: str,
) -> tuple[str | None, str | None]:
    """Configures T3 Code runtime pairing state and retrieves the pairing URL and QR code."""
    clean_url = t3_url.rstrip("/")
    try:
        cfg = (
            f"import json, os, time\nurl = {json.dumps(clean_url)}\nhost = {json.dumps(ssh_host)}\n"
            "os.makedirs('/root/.t3', exist_ok=True)\n"
            "open('/root/.t3/public_url', 'w').write(url + '\\n')\n"
            "try:\n open('/etc/machine-info', 'w').write(f'PRETTY_HOSTNAME=\"{host}\"\\n')\n"
            "except Exception: pass\n"
            "for p in ['/etc/environment', '/root/.bashrc']:\n"
            " try:\n"
            "  c = open(p).read() if os.path.exists(p) else ''\n"
            "  with open(p, 'a+') as f:\n"
            "   if 'T3_PUBLIC_URL=' not in c: f.write(f'export T3_PUBLIC_URL=\"{url}\"\\n')\n"
            "   if 'T3_SSH_HOST=' not in c: f.write(f'export T3_SSH_HOST=\"{host}\"\\n')\n"
            " except Exception: pass\n"
            "rt = '/root/.t3/userdata/server-runtime.json'\n"
            "for _ in range(20):\n"
            " if os.path.isfile(rt):\n"
            "  try:\n"
            "   d = json.load(open(rt))\n"
            "   if d.get('devUrl') != url:\n"
            "    d['devUrl'] = url\n"
            "    json.dump(d, open(rt + '.tmp', 'w'), indent=2)\n"
            "    os.replace(rt + '.tmp', rt)\n"
            "   break\n"
            "  except Exception: pass\n"
            " time.sleep(0.25)\n"
        )
        sandbox.exec("python3", "-c", cfg).wait()
    except Exception as exc:
        logger.debug("Failed configuring T3 runtime state: %s", exc)

    pair_url, qr_code = None, None
    try:
        p = sandbox.exec("t3", "auth", "pairing", "create", "--ttl", "24h", "--json")
        if p.wait() == 0:
            cred = json.loads(p.stdout.read().strip()).get("credential")
            if cred:
                pair_url = f"{clean_url}/pair#token={cred}"
                qr_code = generate_ascii_qr(pair_url)
    except Exception as exc:
        logger.debug("Failed running t3 auth pairing create: %s", exc)

    if not pair_url:
        for _ in range(25):
            try:
                p = sandbox.exec("cat", "/tmp/t3-pairing.json")
                if p.wait() == 0:
                    cred = json.loads(p.stdout.read().strip()).get("credential")
                    if cred:
                        pair_url = f"{clean_url}/pair#token={cred}"
                        qr_code = generate_ascii_qr(pair_url)
                        break
            except Exception:
                pass
            time.sleep(1.0)

    return pair_url or clean_url, qr_code
