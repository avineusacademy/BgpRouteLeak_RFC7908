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
    return run_command(router, "show ip bgp detail")

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
# Parse BGP detail output for prefixes with LocalPref, Community
# ------------------------------
def parse_bgp_detail(output: str):
    """
    Parses "show ip bgp detail" output.
    Returns dict:
      prefix -> dict with keys: 'local_pref', 'community', 'as_path' (list)
    """
    prefix_info = {}
    current_prefix = None
    local_pref = None
    community = None
    as_path = []
    in_path_section = False

    for line in output.splitlines():
        line = line.strip()
        if line.startswith("BGP routing table entry for"):
            # New prefix section
            current_prefix = line.split("for")[1].split(",")[0].strip()
            local_pref = None
            community = None
            as_path = []
            in_path_section = False
            prefix_info[current_prefix] = {
                'local_pref': None,
                'community': None,
                'as_path': []
            }
        elif current_prefix:
            # Check for local pref line
            lp_match = re.search(r'Local preference:?\s*(\d+)', line, re.IGNORECASE)
            if lp_match:
                local_pref = lp_match.group(1)
                prefix_info[current_prefix]['local_pref'] = local_pref
            # Sometimes local pref appears simply as "LocalPref: 100"
            elif line.lower().startswith("localpref") or line.lower().startswith("local preference"):
                # Try extract local pref
                lp_val = re.findall(r'(\d+)', line)
                if lp_val:
                    local_pref = lp_val[0]
                    prefix_info[current_prefix]['local_pref'] = local_pref

            # Community line can appear as "Community: 100:100"
            comm_match = re.search(r'Community:\s*([0-9: ]+)', line, re.IGNORECASE)
            if comm_match:
                community = comm_match.group(1).strip()
                prefix_info[current_prefix]['community'] = community

            # AS path is usually on line with "X Y Z" AS numbers before "from"
            # Example: "200 65003" or "65003 200"
            aspath_match = re.match(r'^([0-9 ]+)\s+from', line)
            if aspath_match:
                as_path_str = aspath_match.group(1).strip()
                as_path = as_path_str.split()
                prefix_info[current_prefix]['as_path'] = as_path

    return prefix_info

# ------------------------------
# Draw topology with prefixes and leak highlighting
# ------------------------------
def draw_topology_figure(highlight_leak_only, show_lp_comm, leak_type):
    routers = ["r1", "r2", "r3"]
    G = nx.DiGraph()
    node_labels = {}

    # Get AS numbers for nodes
    router_asn = {r: get_as_number(r) for r in routers}

    # Parse BGP details for each router
    router_bgp_attrs = {}
    for r in routers:
        bgp_detail = run_command(r, "show ip bgp detail")
        router_bgp_attrs[r] = parse_bgp_detail(bgp_detail)

    # Define prefixes leaked on r1 in type1 leak (example)
    leaked_prefixes_r1 = []
    if leak_type == "type1":
        # For demo, consider prefixes learned from r2 leaked on r1
        for prefix, attrs in router_bgp_attrs.get("r1", {}).items():
            # If AS path includes r2's ASN (200) but prefix is on r1, mark as leaked
            if "200" in attrs.get('as_path', []):
                leaked_prefixes_r1.append(prefix)

    # Add nodes
    for r in routers:
        label = f"{r}\n{router_asn[r]}"
        G.add_node(r, label=label)
        node_labels[r] = label

    # Map interfaces to IP for link drawing
    ip_map_per_router = {}
    for r in routers:
        ip_map_per_router[r] = get_interface_ip_map(r)

    ip_to_router_iface = {}
    for r, ip_map in ip_map_per_router.items():
        for ip, iface in ip_map.items():
            ip_to_router_iface[ip] = (r, iface)

    # Find links by subnet match
    links = []
    for ip1, (r1, i1) in ip_to_router_iface.items():
        for ip2, (r2, i2) in ip_to_router_iface.items():
            if r1 != r2 and ip1 != ip2:
                if in_same_subnet(ip1, ip2, mask=30):
                    link = tuple(sorted([(r1, i1, ip1), (r2, i2, ip2)]))
                    if link not in links:
                        links.append(link)

    # Add edges
    for (r1, i1, ip1), (r2, i2, ip2) in links:
        # Color edges red if it is leak path r1->r3 in type1
        if leak_type == "type1":
            # For demo: leak path is r1 -> r3 edge
            if (r1 == "r1" and r2 == "r3") or (r1 == "r3" and r2 == "r1"):
                G.add_edge(r1, r2, color='red')
            else:
                G.add_edge(r1, r2, color='black')
        else:
            G.add_edge(r1, r2, color='black')

    pos = nx.spring_layout(G, seed=42)
    fig, ax = plt.subplots(figsize=(10, 6))

    # Draw nodes
    nx.draw_networkx_nodes(G, pos, node_size=2500, node_color='lightblue', ax=ax)
    nx.draw_networkx_labels(G, pos, labels=node_labels, font_weight='bold', font_size=10, ax=ax)

    # Draw edges with colors
    edges = G.edges(data=True)
    edge_colors = [edata.get('color', 'black') for _, _, edata in edges]
    nx.draw_networkx_edges(G, pos, edge_color=edge_colors, arrowsize=20, ax=ax)

    # Draw prefixes under each node
    for r in routers:
        x, y = pos[r]
        attrs = router_bgp_attrs[r]
        displayed_count = 0
        for prefix, attr in attrs.items():
            # Skip prefixes in highlight leak only mode if not leaked
            is_leaked = (r == "r1" and prefix in leaked_prefixes_r1)
            if highlight_leak_only and not is_leaked:
                continue

            # Compose prefix text
            prefix_text = prefix
            if show_lp_comm:
                parts = []
                if attr.get('local_pref'):
                    parts.append(f"LP:{attr['local_pref']}")
                if attr.get('community'):
                    parts.append(f"Comm:{attr['community']}")
                if parts:
                    prefix_text += " [" + ", ".join(parts) + "]"

            prefix_y = y - 0.12 - displayed_count * 0.07
            displayed_count += 1

            # Draw leak marker circle left of prefix text if leaked
            if is_leaked:
                ax.plot(x - 0.07, prefix_y, marker='o', markersize=8, color='red', markeredgecolor='black')

            # Draw prefix text in black with white background box for clarity
            ax.text(x, prefix_y, prefix_text, fontsize=8, ha='center', va='center',
                    fontfamily='monospace', color='black',
                    bbox=dict(facecolor='white', edgecolor='black', boxstyle='round,pad=0.2'))

    # Legend for leak marker
    ax.plot([], [], marker='o', color='red', markeredgecolor='black', linestyle='None', label='Leaked Prefix')
    ax.legend(loc='upper right', fontsize=9, frameon=True)

    plt.axis('off')
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

    st.markdown("---")
    show_lp_comm = st.checkbox("Show Local Preference & Community", value=False)
    highlight_leak_only = st.checkbox("Highlight Leaked Prefixes Only", value=False)

# Leak application
if apply_button:
    output = apply_leak(selected_router, selected_leak)
    st.sidebar.text_area("Leak Application Output", output, height=150)

# Leak description
st.header("Leak Type Description")
st.write(leak_description(selected_leak))

# Topology Diagram
st.header("Network Topology with Prefixes, Local Pref & Community")
fig = draw_topology_figure(highlight_leak_only, show_lp_comm, selected_leak)
topology_img = BytesIO()
fig.savefig(topology_img, format='png')
topology_img.seek(0)
st.pyplot(fig)
plt.close(fig)

# Fetch and show router details
if fetch_button:
    details = get_router_details(fetch_router)
    st.header(f"Live Routing Info for {fetch_router}")
    st.text_area(f"Router {fetch_router} Routing Info", details, height=300)

# Export PDF button
if st.button("Export Report to PDF"):
    # Save figure to BytesIO
    img_bytes = BytesIO()
    fig.savefig(img_bytes, format="png")
    img_bytes.seek(0)

    route_tables = {}
    for r in routers:
        route_tables[r] = fetch_routes(r)

    pdf_bytes = export_pdf(img_bytes, route_tables)
    st.download_button(label="Download PDF Report", data=pdf_bytes, file_name="bgp_leak_report.pdf", mime="application/pdf")
