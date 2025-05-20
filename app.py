#!/usr/bin/env python3
"""
Fetch MikroTik interface information and save it to interfaces.html
"""

import os
import html
import webbrowser
from datetime import datetime
from routeros_api import RouterOsApiPool

# ── Credentials ────────────────────────────────────────────────────────────────
# For production, store these in environment variables or a .env file!
MT_HOST = os.getenv("MT_HOST", "") #add ip address of router 
MT_USER = os.getenv("MT_USER", "") #add user name 
MT_PASS = os.getenv("MT_PASS", "") #add password
MT_PORT = int(os.getenv("MT_PORT", "8728"))        # change if you use a custom API port

# ── Connect & fetch data ───────────────────────────────────────────────────────
try:
    pool = RouterOsApiPool(
        host=MT_HOST,
        username=MT_USER,
        password=MT_PASS,
        port=MT_PORT,
        plaintext_login=True,
        use_ssl=False,          # enable if you’ve configured SSL (API-SSL)
    )
    api = pool.get_api()

    iface_resource = api.get_resource("interface")
    interfaces = iface_resource.get()
    pool.disconnect()

except Exception as e:
    raise SystemExit(f"❌ Connection failed: {e}")

# ── Build HTML ────────────────────────────────────────────────────────────────
# determine all possible keys in the returned dicts so the table is complete
all_keys = sorted({key for row in interfaces for key in row if not key.startswith(".")})

def td(value):
    """Escape/format table cells neatly."""
    if isinstance(value, bool):
        value = "✅" if value else "❌"
    return f"<td>{html.escape(str(value))}</td>"

rows_html = "\n".join(
    "  <tr>" + "".join(td(i.get(k, "")) for k in all_keys) + "</tr>"
    for i in interfaces
)

generated_at = datetime.now().strftime("%Y‑%m‑%d %H:%M:%S")

html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>MikroTik Interfaces</title>
<style>
    body{{font-family:Arial,Helvetica,sans-serif;margin:2rem;background:#f8f9fa;}}
    h1{{margin-bottom:0.2rem}}
    table{{border-collapse:collapse;width:100%;background:white}}
    th,td{{border:1px solid #dee2e6;padding:0.5rem;font-size:0.9rem;text-align:left}}
    th{{background:#343a40;color:#fff;position:sticky;top:0}}
    tr:nth-child(even){{background:#f1f3f5}}
    .generated{{margin-top:0.5rem;font-size:0.8rem;color:#6c757d}}
</style>
</head>
<body>
<h1>MikroTik Interfaces</h1>
<div class="generated">Generated at {generated_at}</div>
<table>
  <thead>
    <tr>{"".join(f"<th>{html.escape(k)}</th>" for k in all_keys)}</tr>
  </thead>
  <tbody>
{rows_html}
  </tbody>
</table>
</body>
</html>"""

# ── Write file & open ──────────────────────────────────────────────────────────
outfile = "interfaces.html"
with open(outfile, "w", encoding="utf-8") as f:
    f.write(html_doc)

print(f"✅ Interface list saved to {outfile}")
webbrowser.open_new_tab(os.path.abspath(outfile))  # comment out if you prefer not to auto‑open
