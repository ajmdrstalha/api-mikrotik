#!/usr/bin/env python3
"""
Tiny web app to view MikroTik interfaces and change the IP address of any
interface via the RouterOS API.

Requirements:
    pip install flask routeros-api python-dotenv  # python-dotenv optional
"""

import os
import html
import ipaddress
from flask import Flask, render_template_string, request, redirect, url_for, flash
from routeros_api import RouterOsApiPool
from dotenv import load_dotenv   # harmless if .env is absent

# ─── Configuration ─────────────────────────────────────────────────────────────
load_dotenv()   # pull MT_HOST, MT_USER... from a .env file if present

MT_HOST = os.getenv("MT_HOST", "27.131.13.150")
MT_USER = os.getenv("MT_USER", "talha")
MT_PASS = os.getenv("MT_PASS", "jis2010#")
MT_PORT = int(os.getenv("MT_PORT", "8728"))           # API port

# ─── Helper to (re)connect quickly ─────────────────────────────────────────────
def get_api_pool():
    return RouterOsApiPool(
        host=MT_HOST,
        username=MT_USER,
        password=MT_PASS,
        port=MT_PORT,
        plaintext_login=True,
        use_ssl=False,          # flip to True if you use API‑SSL
    )

# ─── Flask app set‑up ──────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.urandom(16)   # only for flash() messages

# ─── Jinja2 template, kept inline for a self‑contained file ────────────────────
PAGE = """
<!doctype html>
<title>MikroTik Interface Manager</title>
<link rel="stylesheet"
      href="https://cdn.jsdelivr.net/npm/bulma@0.9.4/css/bulma.min.css">
<section class="section">
<div class="container">
  <h1 class="title">MikroTik Interfaces</h1>

  {% with msgs = get_flashed_messages() %}
    {% if msgs %}
      <div class="notification is-primary">{{ msgs[0] }}</div>
    {% endif %}
  {% endwith %}

  <table class="table is-striped is-fullwidth">
    <thead>
      <tr>
        <th>Name</th> <th>Type</th> <th>Running</th>
        <th style="min-width:200px">Current&nbsp;IP(s)</th>
        <th style="min-width:240px">Assign&nbsp;New&nbsp;IP/CIDR</th>
      </tr>
    </thead>
    <tbody>
    {% for i in ifaces %}
      <tr>
        <td>{{ i["name"] }}</td>
        <td>{{ i.get("type","") }}</td>
        <td>{{ "✅" if i.get("running") else "❌" }}</td>
        <td>
          {% for ip in i["ips"] %}
            <span class="tag is-link">{{ ip }}</span>
          {% endfor %}
        </td>
        <td>
          <form method="post" action="{{ url_for('update_ip') }}">
            <input type="hidden" name="iface" value="{{ i['name'] }}">
            <div class="field has-addons">
              <div class="control is-expanded">
                <input class="input" type="text" name="new_ip"
                       placeholder="192.168.88.1/24" required>
              </div>
              <div class="control">
                <button class="button is-info">Set</button>
              </div>
            </div>
          </form>
        </td>
      </tr>
    {% endfor %}
    </tbody>
  </table>
</div>
</section>
"""

# ─── Routes ────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    try:
        pool = get_api_pool()
        api = pool.get_api()

        iface_res = api.get_resource("interface")
        ip_res = api.get_resource("ip/address")

        ifaces = iface_res.get()
        ip_rows = ip_res.get()

        # map interface‑name → list of address strings
        ip_map = {}
        for row in ip_rows:
            ip_map.setdefault(row["interface"], []).append(row["address"])

        for iface in ifaces:
            iface["ips"] = ip_map.get(iface["name"], [])

        return render_template_string(PAGE, ifaces=ifaces)
    except Exception as e:
        flash(f"Error connecting to router: {str(e)}")
        return render_template_string(PAGE, ifaces=[])
    finally:
        if 'pool' in locals():
            pool.disconnect()


@app.route("/update", methods=["POST"])
def update_ip():
    iface = request.form["iface"]
    new_ip = request.form["new_ip"].strip()  # remove any whitespace

    try:
        # Validate the IP address format
        ipaddress.ip_interface(new_ip)
    except ValueError:
        flash("Invalid IP address format! Please use format like 192.168.1.1/24")
        return redirect(url_for("index"))

    pool = get_api_pool()
    api = pool.get_api()
    ip_res = api.get_resource("ip/address")

    try:
        # 1️⃣ remove existing IPs for that interface
        for row in ip_res.get():
            if row["interface"] == iface:
                ip_res.remove(id=row[".id"])

        # 2️⃣ add the new address
        ip_res.add(address=new_ip, interface=iface)
        flash(f"{html.escape(iface)} → {html.escape(new_ip)} applied successfully!")
    except Exception as e:
        flash(f"Error applying changes: {str(e)}")
    finally:
        pool.disconnect()

    return redirect(url_for("index"))


# ─── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"Serving on http://127.0.0.1:5000  →  logs show here ⤵︎")
    app.run(debug=True)