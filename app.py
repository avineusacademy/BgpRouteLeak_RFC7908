import streamlit as st
import subprocess
import networkx as nx
import matplotlib.pyplot as plt
from io import BytesIO
from fpdf import FPDF

def apply_leak(router: str, leak_type: str) -> str:
    if leak_type == "none":
        leak_type = "cleanup"
    cmd = f"/scripts/apply_leak.sh {router} {leak_type}"
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=20)
        return result.stdout + result.stderr
    except Exception as e:
        return f"Error applying leak: {e}"

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

def draw_topology_figure():
    G = nx.DiGraph()
    nodes = {"r1": "AS65001", "r2": "AS200", "r3": "AS65003"}
    for r, asn in nodes.items():
        G.add_node(r, label=f"{r}\n{asn}")
    edges = [("r1", "r2"), ("r2", "r1"), ("r2", "r3"), ("r3", "r2")]
    G.add_edges_from(edges)

    pos = nx.spring_layout(G, seed=42)
    fig, ax = plt.subplots(figsize=(6, 4))
    nx.draw(G, pos, with_labels=True, labels=nx.get_node_attributes(G, 'label'),
            node_size=2000, node_color='skyblue', font_size=10, font_weight='bold', arrowsize=20, ax=ax)
    plt.tight_layout()
    return fig

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

st.title("BGP Route Leak Simulator")

routers = ["r1", "r2", "r3"]
leak_types = ["none", "type1", "type2", "type3", "type4", "type5", "type6"]

with st.sidebar:
    selected_router = st.selectbox("Select Router to simulate leak", routers)
    selected_leak = st.selectbox("Select Leak Type", leak_types)
    apply_button = st.button("Apply Leak")
    fetch_router = st.selectbox("Select Router to fetch routes", routers)
    fetch_button = st.button("Fetch Live Routes")

if apply_button:
    output = apply_leak(selected_router, selected_leak)
    st.sidebar.text_area("Leak Application Output", output, height=150)

st.header("Leak Type Description")
st.write(leak_description(selected_leak))

st.header("Network Topology")
fig = draw_topology_figure()
topology_img = BytesIO()
fig.savefig(topology_img, format='png')
topology_img.seek(0)
st.pyplot(fig)

st.header("Live BGP Routes")
if fetch_button:
    routes = fetch_routes(fetch_router)
    st.text_area(f"BGP Routes on {fetch_router}", routes, height=300)

st.header("Export Report")
if st.button("Generate PDF Report"):
    route_tables = {r: fetch_routes(r) for r in routers}
    pdf_bytes = export_pdf(topology_img, route_tables)
    st.download_button(label="Download PDF Report",
                       data=pdf_bytes,
                       file_name="bgp_route_leak_report.pdf",
                       mime="application/pdf")
