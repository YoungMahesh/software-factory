#!/usr/bin/env bash
REAL_T3="/opt/t3/t3"

if [ "${1:-}" = "pair" ]; then
    PUBLIC_URL="${T3_PUBLIC_URL:-}"
    if [ -z "$PUBLIC_URL" ] && [ -f "/root/.t3/public_url" ]; then
        PUBLIC_URL=$(cat /root/.t3/public_url 2>/dev/null | tr -d '\r\n')
    fi

    if [ -n "$PUBLIC_URL" ]; then
        export T3_PUBLIC_URL="$PUBLIC_URL"
        python3 -c "
import json, os, sys

url = sys.argv[1]
candidates = [
    '/root/.t3/userdata/server-runtime.json',
    '/root/.t3/dev/server-runtime.json',
]

for p in candidates:
    if os.path.isfile(p):
        try:
            with open(p, 'r') as f:
                d = json.load(f)
            if d.get('devUrl') != url:
                d['devUrl'] = url
                tmp = p + '.tmp'
                with open(tmp, 'w') as f:
                    json.dump(d, f, indent=2)
                os.replace(tmp, p)
        except Exception:
            pass
" "$PUBLIC_URL" 2>/dev/null || true
    fi

    has_base_dir=0
    for arg in "$@"; do
        if [ "$arg" = "--base-dir" ] || [[ "$arg" == --base-dir=* ]]; then
            has_base_dir=1
            break
        fi
    done

    if [ "$has_base_dir" -eq 0 ]; then
        if [ ! -f ".t3/userdata/server-runtime.json" ] && [ -f "/root/.t3/userdata/server-runtime.json" ]; then
            set -- "$@" --base-dir /root/.t3
        fi
    fi
fi

exec "$REAL_T3" "$@"
