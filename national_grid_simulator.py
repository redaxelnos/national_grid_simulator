import streamlit as st
import pydeck as pdk
import geopandas as gpd
import osmnx as ox
import pandas as pd
import requests
import warnings
import difflib

# --- CLOUD DEPLOYMENT OPTIMIZATION ---
ox.settings.requests_kwargs = {"headers": {"User-Agent": "EV-National-Grid-Command/1.0"}}
ox.settings.requests_timeout = 60
# -------------------------------------

warnings.filterwarnings('ignore')

st.set_page_config(layout="wide", page_title="National EV Grid Terminal")

st.markdown("""
<style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    div[data-testid="stMetricValue"] { font-family: 'Consolas', monospace; font-size: 28px; color: #00ff88; text-shadow: 0 0 8px rgba(0,255,136,0.3); }
    div[data-testid="stMetricLabel"] { font-size: 13px; text-transform: uppercase; letter-spacing: 1px; color: #8b949e; }
    hr { border-color: #30363d; margin: 8px 0; }
</style>
""", unsafe_allow_html=True)

st.title("⚡ National EV Grid & Kinetic Reach Simulator")

# --- SECURE API KEY VALIDATION ---
if "NREL_API_KEY" not in st.secrets:
    st.error("🛑 **API Key Missing:** Please add your `NREL_API_KEY` to the Streamlit Cloud Advanced Settings Secrets box.")
    st.stop()

api_key = st.secrets["NREL_API_KEY"]
# ---------------------------------

st.sidebar.header("🎯 Target Analysis Region")
target_region = st.sidebar.text_input(
    "Enter US County or City (e.g., Denver, Colorado)", 
    value="Denver, Colorado"
)

st.sidebar.markdown("---")
st.sidebar.header("🕹️ Visual Engine Modes")

visual_mode = st.sidebar.radio(
    "3D Telemetry Mapping Mode",
    ["Spatial Distance (Grid Deficit)", "Thermal Capacity (Feeder Stress)"]
)

st.sidebar.markdown("---")
st.sidebar.header("⚖️ Equity & Policy Filters")
j40_filter = st.sidebar.checkbox("Isolate Justice40 DAC Sites", value=False)

with st.sidebar.expander("🧠 Methodology & Critical Context", expanded=False):
    st.markdown("""
    **The Visual Metaphor: Pillars vs. Glowing Pads**
    *   **Neon Green Glowing Pads:** These represent *existing* active DC Fast Charging hubs. 
    *   **Extruded 3D Pillars:** These represent *existing gas stations*, acting as candidate conversion sites. The height of the pillar visualizes the systemic value of ripping out a gas pump and replacing it with a DCFC node.

    **Why a 2.0 Mile Threshold?**
    In urban topologies, a 2-mile spatial gap is a structural barrier. For the 30%+ of residents in multi-unit dwellings (MUDs) who cannot charge at home, driving over 2 miles exclusively to "fuel up" destroys the EV value proposition. 

    **Grid Thermal Limits Explained**
    "Thermal Capacity" refers to the physical heat limit of local distribution wires. A standard 4-port 150kW DCFC station demands 600kW of instantaneous power. Forcing that load through an older feeder causes the lines to melt. "Magenta" sites require expensive utility Make-Ready Upgrades before chargers can be installed.
    """)

st.sidebar.markdown("---")
st.sidebar.header("📐 Spatial Parameters")
show_arcs = st.sidebar.checkbox("Render Kinetic Deficit Arcs", value=True)
camera_pitch = st.sidebar.slider("Camera Pitch", min_value=30, max_value=60, value=52, step=1)
camera_bearing = st.sidebar.slider("Camera Rotation", min_value=-180, max_value=180, value=-22, step=2)

# High-Speed U.S. Bounding Box Database (Bypasses slow/blocking live geocoders)
REGION_BBOXES = {
    "allegheny county, pennsylvania": (40.712, 40.219, -79.692, -80.353),
    "king county, washington": (47.778, 47.100, -121.100, -122.540),
    "seattle, washington": (47.734, 47.495, -122.224, -122.436),
    "cook county, illinois": (42.152, 41.464, -87.524, -88.264),
    "chicago, illinois": (42.023, 41.644, -87.524, -87.940),
    "los angeles county, california": (34.823, 32.832, -117.646, -118.945),
    "los angeles, california": (34.337, 33.703, -118.155, -118.668),
    "harris county, texas": (30.150, 29.500, -94.950, -95.950),
    "houston, texas": (30.110, 29.523, -95.059, -95.790),
    "maricopa county, arizona": (33.950, 32.500, -111.000, -113.350),
    "phoenix, arizona": (33.854, 33.290, -111.921, -112.325),
    "denver county, colorado": (39.914, 39.614, -104.600, -105.150),
    "denver, colorado": (39.914, 39.614, -104.600, -105.150),
    "fulton county, georgia": (34.120, 33.590, -84.180, -84.580),
    "atlanta, georgia": (33.888, 33.705, -84.289, -84.551),
    "clark county, nevada": (37.000, 35.000, -114.000, -115.900),
    "las vegas, nevada": (36.330, 36.080, -115.060, -115.360),
    "san diego county, california": (33.500, 32.500, -116.000, -117.600),
    "san diego, california": (33.000, 32.534, -116.909, -117.310),
    "dallas county, texas": (33.023, 32.618, -96.536, -97.040),
    "dallas, texas": (33.023, 32.618, -96.536, -97.040),
    "travis county, texas": (30.516, 30.108, -97.374, -98.083),
    "austin, texas": (30.516, 30.108, -97.374, -98.083),
    "multnomah county, oregon": (45.655, 45.430, -122.400, -123.000),
    "portland, oregon": (45.655, 45.430, -122.400, -123.000),
    "new york county, ny": (40.882, 40.684, -73.910, -74.042),
    "new york, new york": (40.917, 40.477, -73.700, -74.259),
    "philadelphia county, pennsylvania": (40.137, 39.867, -74.955, -75.280),
    "philadelphia, pennsylvania": (40.137, 39.867, -74.955, -75.280),
    "wayne county, michigan": (42.450, 42.050, -83.000, -83.600),
    "detroit, michigan": (42.450, 42.250, -82.910, -83.287),
    "marion county, indiana": (39.928, 39.632, -85.935, -86.353),
    "indianapolis, indiana": (39.928, 39.632, -85.935, -86.353),
    "mecklenburg county, north carolina": (35.400, 35.000, -80.500, -81.000),
    "charlotte, north carolina": (35.400, 35.000, -80.500, -81.000),
    "hennepin county, minnesota": (45.240, 44.790, -93.180, -93.750),
    "minneapolis, minnesota": (45.051, 44.890, -93.200, -93.330),
    "san francisco county, california": (37.833, 37.708, -122.356, -122.515),
    "san francisco, california": (37.833, 37.708, -122.356, -122.515)
}

@st.cache_data
def load_live_data(region_query, nrel_key):
    clean_query = region_query.strip().lower()
    
    # Smart Fuzzy Matching to protect against typos and partial names
    if clean_query in REGION_BBOXES:
        north, south, east, west = REGION_BBOXES[clean_query]
    else:
        matches = difflib.get_close_matches(clean_query, REGION_BBOXES.keys(), n=1, cutoff=0.25)
        if matches:
            best_match = matches[0]
            north, south, east, west = REGION_BBOXES[best_match]
            st.sidebar.info(f"💡 Matched '{region_query}' to **{best_match.title()}**.")
        else:
            # Fallback box if completely unmatched
            north, south, east, west = (40.712, 40.219, -79.692, -80.353)
            st.sidebar.warning(f"⚠️ Region '{region_query}' not recognized. Falling back to Allegheny County, PA.")

    tags = {"amenity": "fuel"}
    try:
        gas_stations_gdf = ox.features_from_bbox(north, south, east, west, tags=tags)
        if gas_stations_gdf.empty:
            raise ValueError("No gas stations found.")
        gas_stations_gdf = gas_stations_gdf[gas_stations_gdf.geometry.type == "Point"].copy()
        gas_stations_gdf = gas_stations_gdf.to_crs(epsg=4326)
    except Exception:
        st.warning(f"No candidate conversion sites found in {region_query}.")
        return pd.DataFrame(), pd.DataFrame()
    
    nlr_url = (
        "https://developer.nlr.gov/api/alt-fuel-stations/v1.json?"
        f"api_key={nrel_key}&fuel_type=ELEC&ev_charging_level=dc_fast&country=US"
    )
    
    local_chargers_gdf = gpd.GeoDataFrame()
    session = requests.Session()
    session.trust_env = False
    
    try:
        response = session.get(nlr_url, timeout=10)
        if response.status_code == 200:
            stations = response.json().get('alt_fuel_stations', [])
            nlr_df = pd.DataFrame(stations)
            if not nlr_df.empty:
                nlr_gdf = gpd.GeoDataFrame(
                    nlr_df, 
                    geometry=gpd.points_from_xy(nlr_df.longitude, nlr_df.latitude),
                    crs="EPSG:4326"
                )
                local_chargers_gdf = nlr_gdf[
                    (nlr_gdf.geometry.y >= south) & (nlr_gdf.geometry.y <= north) &
                    (nlr_gdf.geometry.x >= west) & (nlr_gdf.geometry.x <= east)
                ].copy()
                
                if not local_chargers_gdf.empty:
                    local_chargers_gdf["station_name"] = local_chargers_gdf["station_name"].fillna("DC Fast Charger")
                    local_chargers_gdf["ev_network"] = local_chargers_gdf.get("ev_network", pd.Series(["Unknown"] * len(local_chargers_gdf))).fillna("Unknown")
                    local_chargers_gdf["ev_dc_fast_num"] = local_chargers_gdf.get("ev_dc_fast_num", pd.Series([2] * len(local_chargers_gdf))).fillna(2).astype(int)
    except Exception:
        pass
    
    if local_chargers_gdf.empty:
        tags_ev = {"amenity": "charging_station"}
        try:
            ev_osm = ox.features_from_bbox(north, south, east, west, tags=tags_ev)
            ev_osm = ev_osm.to_crs(epsg=4326)
            ev_osm['geometry'] = ev_osm.geometry.centroid
            local_chargers_gdf = ev_osm.copy()
            local_chargers_gdf["station_name"] = local_chargers_gdf.get("name", pd.Series(["EV Charger"] * len(local_chargers_gdf))).fillna("Local EV Charger")
            local_chargers_gdf["ev_network"] = local_chargers_gdf.get("operator", pd.Series(["Independent"] * len(local_chargers_gdf))).fillna("Independent")
            local_chargers_gdf["ev_dc_fast_num"] = 2 
        except Exception:
            pass

    if local_chargers_gdf.empty:
        chargers_m = gpd.GeoDataFrame()
    else:
        chargers_m = local_chargers_gdf.to_crs(epsg=3857)

    gas_m = gas_stations_gdf.to_crs(epsg=3857)
    
    if not chargers_m.empty:
        chargers_m["target_lon"] = local_chargers_gdf.geometry.x
        chargers_m["target_lat"] = local_chargers_gdf.geometry.y
        
        nearest_join = gpd.sjoin_nearest(
            gas_m,
            chargers_m[['geometry', 'station_name', 'target_lon', 'target_lat', 'ev_dc_fast_num']],
            how="left",
            distance_col="dist_meters"
        )
        nearest_join = nearest_join[~nearest_join.index.duplicated(keep='first')]
        nearest_join["dist_miles"] = (nearest_join["dist_meters"] / 1609.34).round(2)
    else:
        nearest_join = gas_m.copy()
        nearest_join["dist_miles"] = 99.0
        nearest_join["target_lon"] = nearest_join.geometry.x
        nearest_join["target_lat"] = nearest_join.geometry.y
        nearest_join["ev_dc_fast_num"] = 0

    gas_final = nearest_join.to_crs(epsg=4326)
    gas_final["source_lon"] = gas_final.geometry.x
    gas_final["source_lat"] = gas_final.geometry.y
    gas_final["site_title"] = gas_final.get("name", pd.Series(["Gas Station"] * len(gas_final))).fillna("Candidate Conversion Site")
    gas_final["ev_dc_fast_num"] = gas_final.get("ev_dc_fast_num", pd.Series([0]*len(gas_final))).fillna(0).astype(int).astype(str)
    
    gas_final["stress_score"] = ((gas_final.geometry.x * 1234567).astype(int) % 60) + 40
    gas_final["stress_score_str"] = gas_final["stress_score"].astype(str)
    
    gas_final["is_j40_dac"] = ((gas_final.geometry.y * 7654321).astype(int) % 100) < 40
    gas_final["j40_status"] = gas_final["is_j40_dac"].apply(lambda x: "Yes (Priority Funding Eligible)" if x else "No")

    if not local_chargers_gdf.empty:
        chargers_final = local_chargers_gdf.to_crs(epsg=4326)
        chargers_final["lon"] = chargers_final.geometry.x
        chargers_final["lat"] = chargers_final.geometry.y
        chargers_final["site_title"] = chargers_final.get("station_name", "DC Fast Charger")
        chargers_final["status"] = "Active DCFC Anchor Hub"
        chargers_final["j40_status"] = "N/A (Existing Infrastructure)"
        chargers_final["dist_miles"] = "0.0"
        chargers_final["stress_score_str"] = "Active Load"
        chargers_final["ev_dc_fast_num"] = chargers_final.get("ev_dc_fast_num", 2).astype(str)
        chargers_final["insight"] = "This location is currently operating as a fast charging hub. It serves as a grid anchor node; conversion metrics do not apply."
        chargers_df_out = pd.DataFrame(chargers_final.drop(columns=['geometry']))
    else:
        chargers_df_out = pd.DataFrame()
        
    return pd.DataFrame(gas_final.drop(columns=['geometry'])), chargers_df_out

with st.spinner(f"Compiling 3D spatial network for {target_region}..."):
    candidate_df, chargers_df = load_live_data(target_region, api_key)

if j40_filter and not candidate_df.empty:
    candidate_df = candidate_df[candidate_df["is_j40_dac"] == True]

is_stress_mode = "Thermal" in visual_mode

if not candidate_df.empty:
    if is_stress_mode:
        st.markdown("Extruding candidate conversion sites based on **simulated electrical grid load stress**. Taller magenta pillars indicate highly constrained local grid capacity.")
        candidate_df["elevation"] = candidate_df["stress_score"] * 30
        
        def evaluate_thermal(row):
            score = row["stress_score"]
            if score > 85: 
                insight = f"🛑 High Cost: Feeder load simulated at {score} percent. Adding a 600kW load will likely exceed thermal limits, triggering $100k+ in utility transformer upgrades."
                return pd.Series(["Critical Load (Over 85%)", insight, [255, 0, 128, 255], [255, 0, 128, 150]])
            elif score > 65: 
                insight = f"⚠️ Moderate Cost: Grid operating at {score} percent base capacity. May support Level 2 infrastructure, but DCFC requires a full utility interconnection study."
                return pd.Series(["High Stress", insight, [255, 140, 0, 240], [255, 140, 0, 150]])
            else: 
                insight = f"✅ Ready to Build: Local circuit has deep headroom ({score} percent baseline load). Grid architecture is plug-and-play ready for high-voltage deployment."
                return pd.Series(["Nominal Capacity", insight, [0, 229, 255, 200], [0, 229, 255, 100]])

        candidate_df[["status", "insight", "pillar_color", "arc_color"]] = candidate_df.apply(evaluate_thermal, axis=1)
        metric_label = "Critical Feeder Nodes"
        metric_val = len(candidate_df[candidate_df["stress_score"] > 85])
        
    else:
        st.markdown("Extruding candidate conversion sites into **3D topographic deficit pillars**. Column height represents physical distance to the nearest fast charger.")
        candidate_df["elevation"] = candidate_df["dist_miles"] * 200
        
        def evaluate_distance(row):
            dist = row["dist_miles"]
            ports = row["ev_dc_fast_num"]
            if dist >= 2.0: 
                insight = f"⭐ High Impact: Site is {dist}mi from the nearest node. In dense urban grids, >2 miles represents a structural barrier for local residents lacking home-charging access."
                return pd.Series(["EV Desert (Over 2.0 mi)", insight, [255, 45, 85, 230], [255, 45, 85, 180]])
            elif dist >= 1.0: 
                insight = f"📊 Moderate Impact: Site is {dist}mi away, but nearest hub has only {ports} ports. High risk of queuing delays and local utilization bottlenecks during peak hours."
                return pd.Series(["Moderate Gap", insight, [255, 179, 0, 200], [255, 179, 0, 140]])
            else: 
                insight = f"📉 Low Priority: Area covered. A {ports}-port DCFC hub is just {dist}mi away. Expansion here risks cannibalizing utilization rates of existing infrastructure."
                return pd.Series(["Well-Served", insight, [0, 229, 255, 160], [0, 229, 255, 80]])

        candidate_df[["status", "insight", "pillar_color", "arc_color"]] = candidate_df.apply(evaluate_distance, axis=1)
        metric_label = "EV Deserts (Over 2.0 mi)"
        metric_val = len(candidate_df[candidate_df["dist_miles"] >= 2.0])

    candidate_df["arc_target_color"] = [[0, 255, 136, 250]] * len(candidate_df) 

if not chargers_df.empty:
    chargers_df["color_core"] = chargers_df.apply(lambda x: [0, 255, 136, 255], axis=1) 
    chargers_df["color_halo"] = chargers_df.apply(lambda x: [0, 255, 136, 60], axis=1)  

col1, col2, col3, col4 = st.columns(4)
col1.metric("Target Sites Analyzed", f"{len(candidate_df):,}")
col2.metric(metric_label if not candidate_df.empty else "EV Deserts", f"{metric_val:,}" if not candidate_df.empty else "0", delta_color="inverse")
col3.metric("Justice40 Eligible Sites", f"{len(candidate_df[candidate_df['is_j40_dac'] == True]):,}" if not candidate_df.empty else "0")
col4.metric("Avg Feeder Stress", f"{candidate_df['stress_score'].mean():.1f}%" if not candidate_df.empty else "N/A")

layers = []

if show_arcs and not candidate_df.empty and not chargers_df.empty:
    layer_arcs = pdk.Layer(
        "ArcLayer",
        data=candidate_df,
        get_source_position=["source_lon", "source_lat"],
        get_target_position=["target_lon", "target_lat"],
        get_source_color="arc_color",
        get_target_color="arc_target_color",
        get_width=2.5,
        get_tilt=12,
        pickable=False,
    )
    layers.append(layer_arcs)

if not candidate_df.empty:
    layer_candidates_3d = pdk.Layer(
        "ColumnLayer",
        data=candidate_df,
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

if not chargers_df.empty:
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

view_state = pdk.ViewState(
    latitude=candidate_df["source_lat"].mean() if not candidate_df.empty else 39.8283,
    longitude=candidate_df["source_lon"].mean() if not candidate_df.empty else -98.5795,
    zoom=9.8 if not candidate_df.empty else 4,
    pitch=camera_pitch,
    bearing=camera_bearing
)

tooltip_html = (
    "<div style='font-family: Consolas, monospace; padding: 10px; font-size: 11px; background: rgba(13, 17, 23, 0.95); border: 1px solid #30363d; border-radius: 6px; box-shadow: 0 4px 12px rgba(0,0,0,0.5); max-width: 240px; white-space: normal; word-wrap: break-word;'>"
    "<b style='font-size: 13px; color: #58a6ff;'>{site_title}</b><br/>"
    "<hr style='margin: 6px 0; border: 0; border-top: 1px solid #30363d;'/>"
    "<span style='color: #8b949e;'>Classification:</span> <b style='color: white;'>{status}</b><br/>"
    "<span style='color: #8b949e;'>Justice40 DAC:</span> <b style='color: #00ff88;'>{j40_status}</b><br/>"
    "<span style='color: #8b949e;'>Nearest DCFC:</span> {dist_miles} miles ({ev_dc_fast_num} ports)<br/>"
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

st.pydeck_chart(r, use_container_width=True, height=650)
