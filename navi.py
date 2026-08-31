import streamlit as st
import pydeck as pdk
import requests
import folium
from folium.plugins import Draw
from streamlit_folium import st_folium
from shapely.geometry import shape
import pandas as pd

# ---------------------------------------------------------
# Grid Terminal CSS Styling
# ---------------------------------------------------------
st.set_page_config(layout="wide", page_title="National EV Grid Pro Terminal")

st.markdown("""
<style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    div[data-testid="stMetricValue"] { font-family: 'Consolas', monospace; font-size: 28px; color: #00ff88; text-shadow: 0 0 8px rgba(0,255,136,0.3); }
    div[data-testid="stMetricLabel"] { font-size: 13px; text-transform: uppercase; letter-spacing: 1px; color: #8b949e; }
    hr { border-color: #30363d; margin: 8px 0; }
</style>
""", unsafe_allow_html=True)

st.title("⚡ EV Grid Command & Kinetic Reach Simulator")

# ---------------------------------------------------------
# Sidebar Controls & Reset Button
# ---------------------------------------------------------
st.sidebar.header("🎯 Spatial Boundary Tool")
st.sidebar.markdown("Use the polygon or rectangle tool on the interactive map below to isolate any corridor or region. PostGIS will instantly calculate distance telemetry.")

if st.sidebar.button("🔄 Reset / Clear Drawn Boundary", use_container_width=True):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

API_URL = "http://localhost:8000/api/analyze-region"

st.sidebar.markdown("---")
st.sidebar.header("📊 Infrastructure Layer Focus")
layer_focus = st.sidebar.radio(
    "Comparative View Mode",
    ["Comparative (Both Layers)", "Candidate Gas Station Retrofits Only", "Existing EV Charging Hubs Only"],
    help="Isolate projected brownfield retrofits vs. existing active EV charging infrastructure to analyze coverage gaps."
)

st.sidebar.markdown("---")
st.sidebar.header("🕹️ Visual Engine Modes")
visual_mode = st.sidebar.radio(
    "3D Telemetry Mapping Mode",
    ["Spatial Distance (Grid Deficit)", "Thermal Capacity (Feeder Stress)"],
    help="Switch between physical distance visualization and simulated grid load capacity."
)

st.sidebar.markdown("---")
st.sidebar.header("⚖️ Equity & Policy Filters")
j40_filter = st.sidebar.checkbox("Isolate Justice40 DAC Sites", value=False, help="Filter candidate sites to Disadvantaged Communities.")

with st.sidebar.expander("🧠 Methodology & Critical Context", expanded=False):
    st.markdown("""
    **The Visual Metaphor: Pillars vs. Glowing Pads**
    *   **Neon Green Glowing Pads:** These represent the *existing* active DC Fast-Charging hubs. They are rendered flat because they have a grid deficit of zero—they are the physical anchors of the current network.
    *   **Extruded 3D Pillars:** These represent existing gas stations, acting as our candidate conversion sites. Why gas stations? They are the ultimate “brownfield” targets for EV infrastructure. They already possess the exact physical footprint required: paved pull-through lanes, heavy-duty canopies, high-visibility lighting, and retail amenities (bathrooms, food) crucial for drivers waiting 20-30 minutes for a charge. The pillar's height visualizes the systemic value of ripping out a gas pump and replacing it with a DCFC node at that specific location.

    **Why a 2.0 Mile Threshold?**
    In urban topologies like Allegheny County, a 2-mile spatial gap is a structural barrier. For the 30%+ of residents in multi-unit dwellings (MUDs) who cannot charge at home, driving over 2 miles exclusively to “fuel up” destroys the EV value proposition. Federal NEVI guidelines prioritize 1-mile buffers from corridors; breaching 2 miles in a metro footprint indicates a stark, unserved “EV Desert.”

    **Grid Thermal Limits Explained:**
    “Thermal Capacity” refers to the physical heat limit of local distribution wires. A standard 4-port 150kW DCFC station demands 600kW of instantaneous power. Forcing that load through an older commercial feeder without upgrades causes the lines to overheat and melt, blowing local transformers. “Magenta” sites require expensive utility Make-Ready Upgrades before chargers can be installed.

    **Justice40 Integration:**
    The Justice40 Initiative mandates that 40% of federal clean energy investments flow to Disadvantaged Communities (DACs). Filtering by Justice40 isolates sites that are eligible for prioritized federal grants, merging grid equity with grid expansion. *(Note: DAC status here is modeled deterministically for demonstration).*
    """)

st.sidebar.markdown("---")
st.sidebar.header("📐 Spatial Parameters")
show_arcs = st.sidebar.checkbox("Render Kinetic Deficit Arcs", value=True)
camera_pitch = st.sidebar.slider("Camera Pitch", min_value=30, max_value=60, value=52, step=1)
camera_bearing = st.sidebar.slider("Camera Rotation", min_value=-180, max_value=180, value=-22, step=2)

# ---------------------------------------------------------
# Interactive Folium Map with Drawing Tools
# ---------------------------------------------------------
m = folium.Map(location=[40.4406, -79.9959], zoom_start=11, tiles="CartoDB dark_matter")
Draw(
    export=False,
    draw_options={
        'polyline': False,
        'circle': False,
        'marker': False,
        'circlemarker': False,
        'polygon': True,
        'rectangle': True
    }
).add_to(m)

draw_output = st_folium(m, width="100%", height=350, key="interactive_map")

active_polygon = None
if draw_output and draw_output.get("last_active_drawing"):
    geom_dict = draw_output["last_active_drawing"]["geometry"]
    active_polygon = shape(geom_dict)

if not active_polygon:
    st.info("👆 Draw a polygon or rectangle on the map above to query your PostGIS database across your national records.")
    st.stop()

# ---------------------------------------------------------
# Query FastAPI Backend & PostGIS (with 60s Timeout)
# ---------------------------------------------------------
with st.spinner("Querying PostGIS spatial engine..."):
    try:
        response = requests.post(
            API_URL, 
            json={"geojson": active_polygon.__geo_interface__}, 
            timeout=60
        )
        if response.status_code == 200:
            res_json = response.json()
            candidate_data = res_json.get("candidates", [])
            charger_data = res_json.get("chargers", [])
        else:
            st.error(f"Backend API Error: {response.status_code} - {response.text}")
            candidate_data, charger_data = [], []
    except requests.exceptions.ConnectionError:
        st.error("Could not connect to FastAPI backend. Ensure `uvicorn api:app --reload --port 8000` is running.")
        candidate_data, charger_data = [], []

if not candidate_data and not charger_data:
    st.warning("No sites found within the drawn boundary. Try drawing a larger box over a metropolitan area like Pittsburgh.")
    st.stop()

df = pd.DataFrame(candidate_data)
chargers_df = pd.DataFrame(charger_data)

# Enrich candidate data if present
if not df.empty:
    df["stress_score"] = ((df["source_lon"].abs() * 1234567).astype(int) % 60) + 40
    df["stress_score_str"] = df["stress_score"].astype(str)
    df["is_j40_dac"] = ((df["source_lat"].abs() * 7654321).astype(int) % 100) < 40
    df["j40_status"] = df["is_j40_dac"].apply(lambda x: "Yes (Priority Funding Eligible)" if x else "No")

    if j40_filter:
        df = df[df["is_j40_dac"] == True]

    is_stress_mode = "Thermal" in visual_mode

    if is_stress_mode:
        df["elevation"] = df["stress_score"] * 30
        def evaluate_thermal(row):
            score = row["stress_score"]
            if score > 85:
                return pd.Series(["Critical Load (>85%)", f"🛑 High Cost: Feeder load at {score}%.", [255, 0, 128, 255], [255, 0, 128, 150]])
            elif score > 65:
                return pd.Series(["High Stress", f"⚠️ Moderate Cost: Grid at {score}% capacity.", [255, 140, 0, 240], [255, 140, 0, 150]])
            else:
                return pd.Series(["Nominal Capacity", f"✅ Ready to Build: Local circuit has headroom ({score}%).", [0, 229, 255, 200], [0, 229, 255, 100]])
        df[["status", "insight", "pillar_color", "arc_color"]] = df.apply(evaluate_thermal, axis=1)
        metric_label = "Critical Feeder Nodes"
        metric_val = len(df[df["stress_score"] > 85])
    else:
        df["elevation"] = df["dist_miles"] * 200
        def evaluate_distance(row):
            dist = row["dist_miles"]
            if dist >= 2.0:
                return pd.Series(["EV Desert (>2.0 mi)", f"⭐ High Impact: Site is {dist}mi from nearest node.", [255, 45, 85, 230], [255, 45, 85, 180]])
            elif dist >= 1.0:
                return pd.Series(["Moderate Gap", f"📊 Moderate Impact: Site is {dist}mi away.", [255, 179, 0, 200], [255, 179, 0, 140]])
            else:
                return pd.Series(["Well-Served", f"📉 Low Priority: Nearest hub is {dist}mi away.", [0, 229, 255, 160], [0, 229, 255, 80]])
        df[["status", "insight", "pillar_color", "arc_color"]] = df.apply(evaluate_distance, axis=1)
        metric_label = "EV Deserts (>=2.0 mi)"
        metric_val = len(df[df["dist_miles"] >= 2.0])

    df["arc_target_color"] = [[0, 255, 136, 250]] * len(df)
    df["site_title"] = df["site_name"]
else:
    metric_label = "EV Deserts"
    metric_val = 0

# Enrich active chargers
if not chargers_df.empty:
    chargers_df["site_title"] = chargers_df["station_name"]
    chargers_df["status"] = "Active DCFC Anchor Hub"
    chargers_df["j40_status"] = "N/A (Existing Infrastructure)"
    chargers_df["dist_miles"] = "0.0"
    chargers_df["stress_score_str"] = "Active Load"
    chargers_df["insight"] = "This location is an active fast charging hub serving as a grid anchor node."
    chargers_df["color_core"] = [[0, 255, 136, 255]] * len(chargers_df)
    chargers_df["color_halo"] = [[0, 255, 136, 60]] * len(chargers_df)

# ---------------------------------------------------------
# Executive KPI Metrics
# ---------------------------------------------------------
col1, col2, col3, col4 = st.columns(4)
col1.metric("Selected Brownfield Sites", f"{len(df):,}")
col2.metric(metric_label, f"{metric_val:,}", delta_color="inverse")
col3.metric("Existing Active EV Hubs", f"{len(chargers_df):,}")
col4.metric("Avg Feeder Stress", f"{df['stress_score'].mean():.1f}%" if not df.empty else "N/A")

# ---------------------------------------------------------
# Dynamic Telemetry & Kinetic Reach Briefing Panel
# ---------------------------------------------------------
st.markdown("---")
st.markdown("### 📡 Dynamic Telemetry & Kinetic Reach Briefing")

kinetic_reach_explanation = (
    "**What is Kinetic Reach?**\n"
    "Kinetic Reach measures the spatial travel distance and logistical energy gap that drivers must bridge "
    "between unserved commercial brownfield sites (gas stations) and the nearest active electrical grid anchor hubs (DCFC chargers). "
    "When rendered as arcs, it maps structural connectivity deficits across regional transit corridors."
)

filter_actions = []
if layer_focus == "Comparative (Both Layers)":
    filter_actions.append("• **Infrastructure Layer:** Dual-layer overlay active, rendering candidate gas station retrofits alongside existing active EV charging anchor hubs.")
elif layer_focus == "Candidate Gas Station Retrofits Only":
    filter_actions.append("• **Infrastructure Layer:** Isolated to candidate brownfield gas station retrofits to evaluate conversion potential.")
else:
    filter_actions.append("• **Infrastructure Layer:** Isolated to existing active DC Fast Charging anchor hubs to audit current network coverage.")

if "Spatial" in visual_mode:
    filter_actions.append("• **Telemetry Mode:** *Spatial Distance (Grid Deficit)* is active. 3D column heights represent physical mileage gaps to the nearest charging hub, flagging commercial 'EV Deserts' (>2.0 mi).")
else:
    filter_actions.append("• **Telemetry Mode:** *Thermal Capacity (Feeder Stress)* is active. 3D column heights and magenta highlights represent local distribution wire heat limits, indicating sites requiring costly utility transformer upgrades.")

if j40_filter:
    filter_actions.append("• **Equity Filter:** *Justice40 DAC Isolation* is enabled. Candidates are filtered strictly to Disadvantaged Communities eligible for prioritized federal clean energy grants.")
else:
    filter_actions.append("• **Equity Filter:** Displaying all regional sites regardless of Justice40 DAC designation.")

if show_arcs and layer_focus != "Existing EV Charging Hubs Only":
    filter_actions.append("• **Kinetic Reach Arcs:** Active. Arcs project vector connections from unserved candidate nodes to their nearest active charging anchors.")
else:
    filter_actions.append("• **Kinetic Reach Arcs:** Hidden or disabled for the active layer view.")

st.info(kinetic_reach_explanation + "\n\n**Active Filter Telemetry Actions:**\n" + "\n".join(filter_actions))
st.markdown("---")

# ---------------------------------------------------------
# PyDeck 3D Visualization Layer (Filtered by Layer Focus)
# ---------------------------------------------------------
layers = []

show_candidates = layer_focus in ["Comparative (Both Layers)", "Candidate Gas Station Retrofits Only"]
show_chargers = layer_focus in ["Comparative (Both Layers)", "Existing EV Charging Hubs Only"]

if show_arcs and show_candidates and not df.empty:
    layer_arcs = pdk.Layer(
        "ArcLayer",
        data=df,
        get_source_position=["source_lon", "source_lat"],
        get_target_position=["target_lon", "target_lat"],
        get_source_color="arc_color",
        get_target_color="arc_target_color",
        get_width=2.5,
        get_tilt=12,
        pickable=False,
    )
    layers.append(layer_arcs)

if show_candidates and not df.empty:
    layer_candidates_3d = pdk.Layer(
        "ColumnLayer",
        data=df,
        get_position=["source_lon", "source_lat"],
        get_elevation="elevation",
        elevation_scale=1,
        radius=130,
        get_fill_color="pillar_color",
        extruded=True,
        pickable=True,
        auto_highlight=True,
    )
    layers.append(layer_candidates_3d)

if show_chargers and not chargers_df.empty:
    layer_hub_halo = pdk.Layer(
        "ScatterplotLayer",
        data=chargers_df,
        get_position=["lon", "lat"],
        get_fill_color="color_halo",
        get_radius=700,
        pickable=False,
    )
    layer_hub_core = pdk.Layer(
        "ColumnLayer",
        data=chargers_df,
        get_position=["lon", "lat"],
        get_elevation=40,
        elevation_scale=1,
        radius=250,
        get_fill_color="color_core",
        extruded=True,
        pickable=True,
        auto_highlight=True,
    )
    layers.extend([layer_hub_halo, layer_hub_core])

centroid = active_polygon.centroid
view_state = pdk.ViewState(latitude=centroid.y, longitude=centroid.x, zoom=11, pitch=camera_pitch, bearing=camera_bearing)

tooltip_html = (
    "<div style='font-family: Consolas, monospace; padding: 10px; font-size: 11px; background: rgba(13, 17, 23, 0.95); border: 1px solid #30363d; border-radius: 6px; box-shadow: 0 4px 12px rgba(0,0,0,0.5); max-width: 240px; white-space: normal; word-wrap: break-word;'>"
    "<b style='font-size: 13px; color: #58a6ff;'>{site_title}</b><br/>"
    "<hr style='margin: 6px 0; border: 0; border-top: 1px solid #30363d;'/>"
    "<span style='color: #8b949e;'>Classification:</span> <b style='color: white;'>{status}</b><br/>"
    "<span style='color: #8b949e;'>Justice40 DAC:</span> <b style='color: #00ff88;'>{j40_status}</b><br/>"
    "<span style='color: #8b949e;'>Nearest DCFC:</span> {dist_miles} miles<br/>"
    "<span style='color: #8b949e;'>Grid Stress:</span> {stress_score_str}% cap<br/>"
    "<hr style='margin: 6px 0; border: 0; border-top: 1px solid #30363d;'/>"
    "<b style='color: #c9d1d9;'>Executive Insight:</b><br/>"
    "<span style='color: #a5d6ff; line-height: 1.3;'>{insight}</span>"
    "</div>"
)

r = pdk.Deck(
    map_style="dark",
    layers=layers,
    initial_view_state=view_state,
    tooltip={"html": tooltip_html, "style": {"color": "white"}}
)

st.pydeck_chart(r, width="stretch", height=650)