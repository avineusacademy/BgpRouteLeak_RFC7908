import streamlit as st
import subprocess
import networkx as nx
import matplotlib.pyplot as plt
from io import BytesIO
from fpdf import FPDF
import re
import ipaddress

# ------------------------------
# Run command inside a router
# ------------------------------
def run_command(router: str, command: str) -> str:
    try:
        docker_cmd = f"docker exec {router} vtysh -c '{command}'"
        result = subprocess.run(docker_cmd, shell=True, capture_output=True, text=True, timeout=15)
        return result.stdout
    except Exception as e:
        return f"Error: {e}"

# ------------------------------
# Apply Leak
# ------------------------------
def apply_leak(router: str, leak_type: str) -> str:
    if leak_type == "none":
        leak_type = "cleanup"
    cmd = f"/bin/bash /app/scripts/apply_leak.sh {router} {leak_type}"
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=20)
        return result.stdout + result.stderr
    except Exception as e:
        return f"Error applying leak: {e}"

# ------------------------------
# Apply R1 Community Config
# ------------------------------
def apply_r1_community_config() -> str:
    cmd = "/bin/bash /app/scripts/apply_r1_config.sh"
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=20)
        return result.stdout + result.stderr
    except Exception as e:
        return f"Error applying R1 community config: {e}"

# ------------------------------
# Fetch BGP Routes
# ------------------------------
def fetch_routes(router: str) -> str:
    return run_command(router, "show ip bgp")

# ------------------------------
# Router Details
# ------------------------------
def get_router_details(router: str) -> str:
    commands = [
        "show ip route bgp",
        "show ip bgp summary",
        "show int brief"
    ]
    output = ""
    for cmd in commands:
        out = run_command(router, cmd)
        output += f"### {cmd}\n{out}\n\n"
    return output

# ------------------------------
# Get ASN from BGP summary
# ------------------------------
def get_as_number(router: str) -> str:
    out = run_command(router, "show ip bgp summary")
    match = re.search(r'local AS number (\d+)', out)
    if match:
        return f"AS{match.group(1)}"
    static_asn = {"r1": "AS100", "r2": "AS200", "r3": "AS65003"}
    return static_asn.get(router, "AS-Unknown")

# ------------------------------
# Get interface-to-IP mapping
# ------------------------------
def get_interface_ip_map(router: str) -> dict:
    out = run_command(router, "show int brief")
    iface_map = {}
    for line in out.splitlines():
        if line.strip() == "" or line.startswith("Interface") or line.startswith("---------"):
            continue
        parts = line.split()
        if len(parts) >= 4:
            iface = parts[0]
            ip_with_mask = parts[3]
            if ip_with_mask != "-" and "/" in ip_with_mask:
                ip = ip_with_mask.split("/")[0]
                iface_map[ip] = iface
    return iface_map

# ------------------------------
# Check if two IPs are in the same subnet
# ------------------------------
def in_same_subnet(ip1, ip2, mask=30):
    try:
        net1 = ipaddress.ip_network(f"{ip1}/{mask}", strict=False)
        return ipaddress.ip_address(ip2) in net1
    except Exception:
        return False

# ------------------------------
# Match interfaces and IPs between routers
# ------------------------------
def get_interface_links(routers):
    ip_to_router_iface = {}
    for router in routers:
        ip_map = get_interface_ip_map(router)
        for ip, iface in ip_map.items():
            ip_to_router_iface[ip] = (router, iface)

    links = []
    for ip1, (r1, i1) in ip_to_router_iface.items():
        for ip2, (r2, i2) in ip_to_router_iface.items():
            if r1 != r2 and ip1 != ip2:
                if in_same_subnet(ip1, ip2, mask=30):
                    link = tuple(sorted([(r1, i1, ip1), (r2, i2, ip2)]))
                    if link not in links:
                        links.append(link)
    return links

# ------------------------------
# Extract prefixes from BGP routes
# ------------------------------
def get_prefixes_from_route_output(output: str) -> list:
    prefixes = []
    for line in output.splitlines():
        match = re.match(r'B.*?(\d+\.\d+\.\d+\.\d+\/\d+)', line)
        if match:
            prefixes.append(match.group(1))
    if not prefixes:
        return ["No prefixes"]
    return prefixes

# ------------------------------
# Draw topology with prefixes
# ------------------------------
def draw_topology_figure_combined():
    routers = ["r1", "r2", "r3"]
    G = nx.DiGraph()
    node_labels = {}

    router_prefixes = {}
    for r in routers:
        route_output = run_command(r, "show ip route bgp")
        prefixes = get_prefixes_from_route_output(route_output)
        router_prefixes[r] = prefixes

    for r in routers:
        asn = get_as_number(r)
        label = f"{r}\n{asn}"
        G.add_node(r, label=label)
        node_labels[r] = label

    ip_map_per_router = {}
    for r in routers:
        ip_map_per_router[r] = get_interface_ip_map(r)

    ip_to_router_iface = {}
    for r, ip_map in ip_map_per_router.items():
        for ip, iface in ip_map.items():
            ip_to_router_iface[ip] = (r, iface)

    links = []
    for ip1, (r1, i1) in ip_to_router_iface.items():
        for ip2, (r2, i2) in ip_to_router_iface.items():
            if r1 != r2 and ip1 != ip2:
                if in_same_subnet(ip1, ip2, mask=30):
                    link = tuple(sorted([(r1, i1, ip1), (r2, i2, ip2)]))
                    if link not in links:
                        links.append(link)

    for (r1, i1, ip1), (r2, i2, ip2) in links:
        G.add_edge(r1, r2)
        G.add_edge(r2, r1)

    pos = nx.spring_layout(G, seed=42)
    fig, ax = plt.subplots(figsize=(8, 5))
    nx.draw(G, pos, with_labels=True, labels=node_labels,
            node_size=2500, node_color='lightblue',
            font_size=10, font_weight='bold', arrowsize=20, ax=ax)

    for r, prefix_list in router_prefixes.items():
        prefix_text = "\n".join(prefix_list) if prefix_list else "No prefixes"
        x, y = pos[r]
        ax.text(x, y - 0.08, prefix_text, fontsize=8, fontfamily='monospace',
                ha='center', va='top',
                bbox=dict(facecolor='white', alpha=0.6, edgecolor='gray', boxstyle='round,pad=0.3'))

    plt.tight_layout()
    return fig

# ------------------------------
# PDF Export
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
# Leak Description
# ------------------------------
def leak_description(leak_type: str) -> str:
    desc = {
        "none": "No leak simulation active.",
        "type1": "Type 1: Export leak — R2 re-advertises a route learned from R1 to R3 without proper policy.",
    }
    return desc.get(leak_type, "Unknown leak type selected.")

# ------------------------------
# Streamlit UI
# ------------------------------
st.set_page_config(page_title="BGP Route Leak Simulator", layout="wide")
st.title("BGP Route Leak Simulator")

routers = ["r1", "r2", "r3"]
leak_types = ["none", "type1"]

# Sidebar controls
with st.sidebar:
    selected_router = st.selectbox("Select Router to simulate leak", routers)
    selected_leak = st.selectbox("Select Leak Type", leak_types)
    apply_button = st.button("Apply Leak")
    fetch_router = st.selectbox("Select Router to fetch routes", routers)
    fetch_button = st.button("Fetch Live Routes")
    st.markdown("---")
    if st.button("Apply R1 Community Config"):
        output = apply_r1_community_config()
        st.text_area("R1 Config Output", output, height=150)

# Leak application
if apply_button:
    output = apply_leak(selected_router, selected_leak)
    st.sidebar.text_area("Leak Application Output", output, height=150)

# Leak description
st.header("Leak Type Description")
st.write(leak_description(selected_leak))

# Topology Diagram
st.header("Network Topology with Interface Mapping and Learned Prefixes")
fig = draw_topology_figure_combined()
topology_img = BytesIO()
fig.savefig(topology_img, format='png')
topology_img.seek(0)
st.pyplot(fig)

# Interface-Level Link Table
st.subheader("Interface-Level Link Table")
links = get_interface_links(routers)
table_data = []
for (r1, i1, ip1), (r2, i2, ip2) in links:
    table_data.append({
        "Router A": r1, "Interface A": i1, "IP A": ip1,
        "Router B": r2, "Interface B": i2, "IP B": ip2
    })
if table_data:
    st.table(table_data)
else:
    st.write("No interface links detected. Check interface IPs or subnet mask.")

# Live BGP Routes
st.header("Live BGP Routes")
if fetch_button:
    routes = fetch_routes(fetch_router)
    st.text_area(f"BGP Routes on {fetch_router}", routes, height=300)

# Router Details
st.header("Router Details")
col1, col2, col3 = st.columns(3)
with col1:
    if st.button("Show r1 Details"):
        st.text_area("Details of r1", get_router_details("r1"), height=400)
with col2:
    if st.button("Show r2 Details"):
        st.text_area("Details of r2", get_router_details("r2"), height=400)
with col3:
    if st.button("Show r3 Details"):
        st.text_area("Details of r3", get_router_details("r3"), height=400)

# Debug Interface Mapping
st.subheader("Debug: Interface-to-IP Mapping")
if st.button("Show Interface IP Maps"):
    for r in routers:
        ip_map = get_interface_ip_map(r)
        st.write(f"Router {r} interface-IP map:")
        if ip_map:
            for ip, iface in ip_map.items():
                st.write(f" - Interface: {iface}, IP: {ip}")
        else:
            st.write("No IPs found or parsing issue.")

# PDF Export
st.header("Export Report")
if st.button("Generate PDF Report"):
    route_tables = {r: fetch_routes(r) for r in routers}
    pdf_bytes = export_pdf(topology_img, route_tables)
    st.download_button(label="Download PDF Report",
                       data=pdf_bytes,
                       file_name="bgp_route_leak_report.pdf",
                       mime="application/pdf")
