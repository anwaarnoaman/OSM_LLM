import streamlit as st
import os
import subprocess
import psycopg2
import time
from datetime import datetime

# --- Config ---
POSTGRES_HOST = "localhost"
POSTGRES_PORT = 5432
POSTGRES_DB = "osm"
POSTGRES_USER = "osmuser"
POSTGRES_PASSWORD = "N123456n"
OSM2PGSQL_BIN = "osm2pgsql"
DATA_DIR = "Datafiles"

os.makedirs(DATA_DIR, exist_ok=True)

if "importing" not in st.session_state:
    st.session_state.importing = False
if "logs" not in st.session_state:
    st.session_state.logs = ""
if "history" not in st.session_state:
    st.session_state.history = []

def wait_for_db():
    st.session_state.logs += "⏳ Checking database connection...\n"
    while True:
        try:
            conn = psycopg2.connect(
                dbname=POSTGRES_DB,
                user=POSTGRES_USER,
                password=POSTGRES_PASSWORD,
                host=POSTGRES_HOST,
                port=POSTGRES_PORT
            )
            conn.close()
            st.session_state.logs += "✅ Database is ready.\n"
            break
        except psycopg2.OperationalError:
            st.session_state.logs += "🔄 Waiting for PostGIS...\n"
            time.sleep(2)

def import_osm(file_path, mode="--create"):
    st.session_state.importing = True
    st.session_state.logs = ""

    wait_for_db()

    st.session_state.logs += f"🚀 Importing `{os.path.basename(file_path)}` with `{mode}`...\n"

    cmd = [
        OSM2PGSQL_BIN,
        "--slim",
        "--hstore",
        mode,
        "--cache", "2000",
        "-d", POSTGRES_DB,
        "-H", POSTGRES_HOST,
        "-P", str(POSTGRES_PORT),
        "-U", POSTGRES_USER,
        file_path
    ]

    env = os.environ.copy()
    env["PGPASSWORD"] = POSTGRES_PASSWORD

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        text=True,
        bufsize=1,
        universal_newlines=True
    )

    log_placeholder = st.empty()
    logs = st.session_state.logs

    # Read output line-by-line and update Streamlit placeholder
    for line in process.stdout:
        logs += line
        log_placeholder.text(logs)
        st.session_state.logs = logs

    process.wait()

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if process.returncode == 0:
        logs += "✅ Import completed successfully.\n"
        status = "Success"
    else:
        logs += f"❌ Import failed with code {process.returncode}.\n"
        status = "Failed"

    log_placeholder.text(logs)
    st.session_state.logs = logs

    st.session_state.history.insert(0, {
        "timestamp": timestamp,
        "file": os.path.basename(file_path),
        "mode": mode,
        "status": status
    })

    st.session_state.importing = False

# --- Streamlit UI ---
st.title("🗺️ OSM to PostGIS Importer")

uploaded_file = st.file_uploader("📤 Upload .osm.pbf file", type=["pbf"])
if uploaded_file:
    dest_path = os.path.join(DATA_DIR, uploaded_file.name)
    with open(dest_path, "wb") as f:
        f.write(uploaded_file.read())
    st.success(f"Uploaded to {dest_path}")

files = [f for f in os.listdir(DATA_DIR) if f.endswith(".pbf")]
if files:
    selected_file = st.selectbox("📁 Select a .osm.pbf file", files)
    import_mode = st.radio("🔧 Import Mode", ["--create", "--append"])

    if st.button("🚀 Start Import") and not st.session_state.importing:
        file_path = os.path.join(DATA_DIR, selected_file)
        import_osm(file_path, import_mode)

if st.session_state.importing or st.session_state.logs:
    st.subheader("📋 Import Logs")
    st.text_area("Logs", st.session_state.logs, height=300, key="logs_area")

if st.session_state.history:
    st.subheader("🕓 Import History")
    st.table([
        {
            "Time": h["timestamp"],
            "File": h["file"],
            "Mode": h["mode"],
            "Status": h["status"]
        } for h in st.session_state.history
    ])
