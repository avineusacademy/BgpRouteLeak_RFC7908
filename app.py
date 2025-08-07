import streamlit as st
import subprocess
import networkx as nx
import matplotlib.pyplot as plt
from io import BytesIO
from fpdf import FPDF
import re

# ------------------------------
# Apply Leak to Router
# ------------------------------
def apply_leak(router: str, leak_type: str) -> str:
    if leak_type == "none":
        leak_type = "cleanup"
    cmd = f"/scripts/apply_leak.sh {router} {leak_type}"
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=20)
        return result.stdout + result.stderr
    except Exception as e:
        return f"Error applying leak: {e}"

# ------------------------------
# Fetch BGP Routes
# ------------------------------
def fetch_routes(router: str) -> str:
    try:
        cmd = f"docker exec {router} vtysh -c 'show ip bgp'"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            return result.stdout
        else:
            return f"Failed to fetch routes from {router}."
    except Exception as e:
        return f"Error fetching routes: {e}"

# ------------------------------
# Router Diagnostic Info
# ------------------------------
def get_router_details(router: str) -> str:
    try:
        commands = [
            "show ip route bgp",
            "show ip bgp summary",
            "show int brief"
        ]
        output = ""
        for cmd in commands:
            docker_cmd = f"docker exec {router} vtysh -c '{cmd}'"
            result = subprocess.run(docker_cmd, shell=True, capture_output=True, text=True, timeout=15)
            output += f"### {cmd}\n{result.stdout or result.stderr}\n\n"
        return output
    except Exception as e:
        return f"Error fetching details for {router}: {e}"

# ------------------------------
# Extract Local ASN
# ------------------------------
def get_as_number(router: str) -> str:
    try:
        cmd = f"docker exec {router} vtysh -c 'show ip bgp summary'"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return "AS-Unknown"

        match = re.search(r'BGP router identifier \S+, local AS number (\d+)', result.stdout)
        if match:
            return f"AS{match.group(1)}"
        else:
            return "AS-Unknown"
    except Exception:
        return "AS-Error"

# ------------------------------
# Extract Peer ASNs
# ------------------------------
def get_peer_asns(router: str) -> list:
    peers = []
    try:
        cmd = f"docker exec {router} vtysh -c 'show ip bgp summary'"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        lines = result.stdout.splitlines()

        start = False
        for line in lines:
            if line.startswith("Neighbor") or re.match(r'^\s*Neighbor', line):
                start = True
                continue
            if start and line.strip():
                parts = line.split()
                if len(parts) >= 3:
                    neighbor_ip = parts[0]
                    remote_as = parts[2]
                    peers.append((neighbor_ip, f"AS{remote_as}"))
        return peers
    except Exception:
        return []

# ------------------------------
# Draw Topology with ASNs
# ------------------------------
def draw_topology_figure():
    routers = ["r1", "r2", "r3"]
    G = nx.DiGraph()
    node_labels = {}
    edge_labels = {}

    ip_to_router = {
        "192.168.12.1": "r1",
        "192.168.12.2": "r2",
        "192.168.23.2": "r2",
        "192.168.23.3": "r3",
    }

    for r in routers:
        asn = get_as_number(r)
        G.add_node(r, label=f"{r}\n{asn}")
        node_labels[r] = f"{r}\n{asn}"

        # Add peers from this router
        for peer_ip, peer_asn in get_peer_asns(r):
            neighbor = ip_to_router.get(peer_ip)
            if neighbor:
                G.add_edge(r, neighbor)
                edge_labels[(r, neighbor)] = peer_asn

    pos = nx.spring_layout(G, seed=42)
    fig, ax = plt.subplots(figsize=(6, 4))
    nx.draw(G, pos, with_labels=True, labels=node_labels,
            node_size=2000, node_color='skyblue', font_size=10, font_weight='bold',
            arrowsize=20, ax=ax)
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_size=8, ax=ax)
    plt.tight_layout()
    return fig

# ------------------------------
# Export PDF Report
# ------------------------------
def export_pdf(topology_img: BytesIO, route_tables: dict):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "BGP Route Leak Simulator Report", 0, 1, "C")

    pdf.cell(0, 10, "Network Topology:", 0, 1)
    pdf.image(topology_img, x=15, w=180)

    pdf.set_font("Arial", "", 10)
    for router, routes in route_tables.items():
        pdf.add_page()
        pdf.cell(0, 10, f"Routes on {router}:", 0, 1)
        pdf.set_font("Courier", "", 8)
        pdf.multi_cell(0, 5, routes)

    return pdf.output(dest='S').encode('latin1')

# ------------------------------
# Leak Type Description
# ------------------------------
def leak_description(leak_type: str) -> str:
    desc = {
        "none": "No leak simulation active.",
        "type1": "Type 1: Simple export leak — routes advertised incorrectly outside the AS.",
        "type2": "Type 2: Export of customer routes to a peer without proper filtering.",
        "type3": "Type 3: Community attribute misconfiguration causing leaks.",
        "type4": "Type 4: AS-path stripping or prepending leak.",
        "type5": "Type 5: Route-map misconfiguration allowing unwanted prefixes.",
        "type6": "Type 6: Prefix-list based leak with automatic cleanup."
    }
    return desc.get(leak_type, "Unknown leak type selected.")

# ------------------------------
# Streamlit UI
# ------------------------------
st.set_page_config(page_title="BGP Route Leak Simulator", layout="wide")
st.title("BGP Route Leak Simulator")

routers = ["r1", "r2", "r3"]
leak_types = ["none", "type1", "type2", "type3", "type4", "type5", "type6"]

# Sidebar Controls
with st.sidebar:
    selected_router = st.selectbox("Select Router to simulate leak", routers)
    selected_leak = st.selectbox("Select Leak Type", leak_types)
    apply_button = st.button("Apply Leak")
    fetch_router = st.selectbox("Select Router to fetch routes", routers)
    fetch_button = st.button("Fetch Live Routes")

if apply_button:
    output = apply_leak(selected_router, selected_leak)
    st.sidebar.text_area("Leak Application Output", output, height=150)

# Leak Description
st.header("Leak Type Description")
st.write(leak_description(selected_leak))

# Topology Visualization
st.header("Network Topology")
fig = draw_topology_figure()
topology_img = BytesIO()
fig.savefig(topology_img, format='png')
topology_img.seek(0)
st.pyplot(fig)

# Live BGP Route Fetch
st.header("Live BGP Routes")
if fetch_button:
    routes = fetch_routes(fetch_router)
    st.text_area(f"BGP Routes on {fetch_router}", routes, height=300)

# Router Details
st.header("Router Details")
col1, col2, col3 = st.columns(3)

with col1:
    if st.button("Show r1 Details"):
        r1_details = get_router_details("r1")
        st.text_area("Details of r1", r1_details, height=400)

with col2:
    if st.button("Show r2 Details"):
        r2_details = get_router_details("r2")
        st.text_area("Details of r2", r2_details, height=400)

with col3:
    if st.button("Show r3 Details"):
        r3_details = get_router_details("r3")
        st.text_area("Details of r3", r3_details, height=400)

# Export Report
st.header("Export Report")
if st.button("Generate PDF Report"):
    route_tables = {r: fetch_routes(r) for r in routers}
    pdf_bytes = export_pdf(topology_img, route_tables)
    st.download_button(label="Download PDF Report",
                       data=pdf_bytes,
                       file_name="bgp_route_leak_report.pdf",
                       mime="application/pdf")
