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
from flask import Flask, render_template_string, request, redirect, url_for, flash, session
from routeros_api import RouterOsApiPool
from dotenv import load_dotenv   # harmless if .env is absent

# ─── Configuration ─────────────────────────────────────────────────────────────
load_dotenv()   # pull MT_HOST, MT_USER... from a .env file if present

app = Flask(__name__)
app.secret_key = os.urandom(16)   # needed for flash messages and session

# ─── Templates ────────────────────────────────────────────────────────────────
LOGIN_PAGE = """
<!doctype html>
<title>MikroTik Login</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bulma@0.9.4/css/bulma.min.css">
<section class="section">
<div class="container">
  <h1 class="title">MikroTik Router Login</h1>
  
  {% with msgs = get_flashed_messages() %}
    {% if msgs %}
      <div class="notification is-danger">{{ msgs[0] }}</div>
    {% endif %}
  {% endwith %}
  
  <form method="post" action="{{ url_for('login') }}">
    <div class="field">
      <label class="label">Router IP/Hostname</label>
      <div class="control">
        <input class="input" type="text" name="host" placeholder="192.168.88.1" required>
      </div>
    </div>
    
    <div class="field">
      <label class="label">API Port</label>
      <div class="control">
        <input class="input" type="number" name="port" value="8728" required>
      </div>
    </div>
    
    <div class="field">
      <label class="label">Username</label>
      <div class="control">
        <input class="input" type="text" name="username" placeholder="admin" required>
      </div>
    </div>
    
    <div class="field">
      <label class="label">Password</label>
      <div class="control">
        <input class="input" type="password" name="password" required>
      </div>
    </div>
    
    <div class="field">
      <div class="control">
        <button class="button is-primary">Connect</button>
      </div>
    </div>
  </form>
</div>
</section>
"""

INTERFACE_PAGE = """
<!doctype html>
<title>MikroTik Interface Manager</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bulma@0.9.4/css/bulma.min.css">
<section class="section">
<div class="container">
  <div class="level">
    <div class="level-left">
      <h1 class="title">MikroTik Interfaces</h1>
    </div>
    <div class="level-right">
      <a href="{{ url_for('logout') }}" class="button is-light">Change Router</a>
    </div>
  </div>

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

# ─── Helper to (re)connect quickly ─────────────────────────────────────────────
def get_api_pool():
    return RouterOsApiPool(
        host=session['host'],
        username=session['username'],
        password=session['password'],
        port=session['port'],
        plaintext_login=True,
        use_ssl=False,
    )

# ─── Routes ────────────────────────────────────────────────────────────────────
@app.route("/", methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        host = request.form['host'].strip()
        port = request.form['port'].strip()
        username = request.form['username'].strip()
        password = request.form['password'].strip()

        # Validate port number
        try:
            port = int(port)
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            flash("Invalid port number. Must be between 1 and 65535")
            return render_template_string(LOGIN_PAGE)

        # Test connection
        try:
            pool = RouterOsApiPool(
                host=host,
                username=username,
                password=password,
                port=port,
                plaintext_login=True,
                use_ssl=False,
            )
            api = pool.get_api()
            api.get_resource('/system/resource').get()
            
            # Store credentials in session
            session['host'] = host
            session['port'] = port
            session['username'] = username
            session['password'] = password
            
            pool.disconnect()
            return redirect(url_for('interface_manager'))
        except Exception as e:
            flash(f"Connection failed: {str(e)}")
            return render_template_string(LOGIN_PAGE)
    
    # Clear any existing session on GET request
    session.clear()
    return render_template_string(LOGIN_PAGE)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route("/interfaces")
def interface_manager():
    if not all(key in session for key in ['host', 'port', 'username', 'password']):
        return redirect(url_for('login'))

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

        return render_template_string(INTERFACE_PAGE, ifaces=ifaces)
    except Exception as e:
        flash(f"Error connecting to router: {str(e)}")
        return redirect(url_for('login'))
    finally:
        if 'pool' in locals():
            pool.disconnect()

@app.route("/update", methods=["POST"])
def update_ip():
    if not all(key in session for key in ['host', 'port', 'username', 'password']):
        return redirect(url_for('login'))

    iface = request.form["iface"]
    new_ip = request.form["new_ip"].strip()  # remove any whitespace

    try:
        # Validate the IP address format
        ipaddress.ip_interface(new_ip)
    except ValueError:
        flash("Invalid IP address format! Please use format like 192.168.1.1/24")
        return redirect(url_for('interface_manager'))

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

    return redirect(url_for('interface_manager'))

# ─── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"Serving on http://127.0.0.1:5000  →  logs show here ⤵︎")
    app.run(debug=True)