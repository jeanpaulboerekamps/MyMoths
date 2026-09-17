from datetime import date, timedelta
import html
import io
import json
import math
from pathlib import Path
import time
import zipfile

import requests

import folium
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from folium.plugins import Draw, HeatMap
from shapely.geometry import Point, shape
from shapely import affinity
from streamlit_folium import st_folium

st.set_page_config(
    page_title="Mijn Nachtvlinders",
    page_icon="🦋",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
.block-container {padding-top: 1rem; padding-bottom: 4rem; max-width: 1200px;}
div.stButton > button, div.stDownloadButton > button {
    min-height: 52px; font-size: 1.02rem; border-radius: 12px; width: 100%;
}
[data-testid="stMetric"] {
    padding: 12px; border: 1px solid rgba(128,128,128,.25); border-radius: 14px;
}
.release-badge {
    display:inline-block; padding:.25rem .65rem; border-radius:999px;
    background:rgba(92,51,145,.12); font-weight:700; margin-bottom:.6rem;
}
.active-area {
    padding:.7rem .9rem; border-radius:14px; background:rgba(92,51,145,.08);
    border-left:4px solid #6f42a6; margin:.2rem 0 .8rem 0;
}
div[data-testid="stFileUploader"]:has(input[accept*=".geojson"]) [data-testid="stFileUploaderDropzone"] {
    padding:.15rem 0; border:0; background:transparent;
}
div[data-testid="stFileUploader"]:has(input[accept*=".geojson"]) [data-testid="stFileUploaderDropzoneInstructions"] {display:none;}
div[data-testid="stFileUploader"]:has(input[accept*=".geojson"]) [data-testid="stFileUploaderDropzone"] button {font-size:0;}
div[data-testid="stFileUploader"]:has(input[accept*=".geojson"]) [data-testid="stFileUploaderDropzone"] button::after {
    content:"Kies gebied"; font-size:1rem;
}
@media (max-width: 768px) {
  .block-container {padding-left: .8rem; padding-right: .8rem;}
}
</style>
""", unsafe_allow_html=True)

st.markdown('<span class="release-badge">Publieksversie 1.1 · Nachtvlinderanalyse</span>', unsafe_allow_html=True)
st.title("🦋 Mijn Nachtvlinders")
st.caption(
    "Kies een gebied en ontdek direct wat je nachtvlinderval heeft opgeleverd."
)

if "areas" not in st.session_state:
    st.session_state.areas = {}
    default_areas_path = Path(__file__).with_name("mijn_nachtvlindergebieden.geojson")
    if default_areas_path.exists():
        try:
            default_areas = json.loads(default_areas_path.read_text(encoding="utf-8"))
            features = (
                default_areas.get("features", [])
                if default_areas.get("type") == "FeatureCollection"
                else [default_areas]
            )
            for index, feature in enumerate(features, 1):
                if feature.get("geometry"):
                    name = (feature.get("properties") or {}).get("name") or f"Gebied {index}"
                    st.session_state.areas[name] = feature["geometry"]
        except Exception:
            pass
if "active_area" not in st.session_state:
    st.session_state.active_area = next(iter(st.session_state.areas), None)
if "occ_df" not in st.session_state:
    st.session_state.occ_df = None
if "sample_df" not in st.session_state:
    st.session_state.sample_df = None
if "target_df" not in st.session_state:
    st.session_state.target_df = None
if "target_meta" not in st.session_state:
    st.session_state.target_meta = {}
if "selected_targets" not in st.session_state:
    st.session_state.selected_targets = []
if "show_area_creator" not in st.session_state:
    st.session_state.show_area_creator = False
if "show_help" not in st.session_state:
    st.session_state.show_help = False
if "show_privacy" not in st.session_state:
    st.session_state.show_privacy = False
if "target_key" not in st.session_state:
    st.session_state.target_key = None

def parse_coord(v):
    if pd.isna(v):
        return None
    s = str(v).strip().replace(",", ".")
    sign = -1 if s.endswith(("S", "W")) else 1
    s = s.rstrip("NSEW")
    try:
        return sign * float(s)
    except Exception:
        return None

@st.cache_data(show_spinner=False, max_entries=6)
def read_zipped_csv_bytes(data):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        csvs = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if not csvs:
            raise ValueError("Geen CSV-bestand gevonden in ZIP.")
        with z.open(csvs[0]) as f:
            return pd.read_csv(f)

def read_zipped_csv(upload):
    return read_zipped_csv_bytes(upload.getvalue())

def classify_file(df):
    cols = set(df.columns)
    if {"Occurrence ID", "Accepted species name", "Count inside"} <= cols:
        return "occurrences"
    if {"Sample ID", "Start Time", "End Time"} <= cols:
        return "samples"
    return None

def prep_occ(df):
    out = df.copy()
    out["datum"] = pd.to_datetime(out["Date"], dayfirst=True, errors="coerce")
    out["lat"] = out["Latitude"].map(parse_coord)
    out["lon"] = out["Longitude"].map(parse_coord)
    out["binnen"] = pd.to_numeric(out["Count inside"], errors="coerce").fillna(0)
    out["buiten"] = pd.to_numeric(out["Count outside"], errors="coerce").fillna(0)
    out["aantal"] = out["binnen"] + out["buiten"]
    out["jaar"] = out["datum"].dt.year
    out["maand"] = out["datum"].dt.month
    out["soort"] = out["Accepted species name"].fillna("Onbekend")
    out["familie"] = out["Family"].fillna("Onbekend")
    return out

def prep_samples(df):
    out = df.copy()
    out["datum"] = pd.to_datetime(out["Date"], dayfirst=True, errors="coerce")
    out["lat"] = out["Latitude"].map(parse_coord)
    out["lon"] = out["Longitude"].map(parse_coord)
    out["jaar"] = out["datum"].dt.year
    out["maand"] = out["datum"].dt.month
    return out

def in_polygon(df, geom):
    poly = shape(geom)
    mask = []
    for _, r in df.iterrows():
        if pd.isna(r.get("lat")) or pd.isna(r.get("lon")):
            mask.append(False)
        else:
            mask.append(poly.covers(Point(float(r["lon"]), float(r["lat"]))))
    return df.loc[mask].copy()


def expanded_bbox(geom, radius_km):
    """Bounding box around the polygon plus an approximate radius in kilometres."""
    poly = shape(geom)
    minx, miny, maxx, maxy = poly.bounds
    mid_lat = (miny + maxy) / 2
    lat_pad = radius_km / 110.574
    lon_scale = max(111.320 * math.cos(math.radians(mid_lat)), 1e-6)
    lon_pad = radius_km / lon_scale
    return {
        "swlat": miny - lat_pad,
        "swlng": minx - lon_pad,
        "nelat": maxy + lat_pad,
        "nelng": maxx + lon_pad,
    }

def distance_to_area_km(lon, lat, geom):
    """
    Approximate shortest distance to the polygon in km.
    For Dutch-scale searches this local longitude correction is sufficiently accurate
    for a 5–50 km target-species screening.
    """
    poly = shape(geom)
    pt = Point(float(lon), float(lat))
    if poly.covers(pt):
        return 0.0
    c = poly.centroid
    xfactor = max(math.cos(math.radians(c.y)), 1e-6)
    scaled_poly = affinity.scale(poly, xfact=xfactor, yfact=1.0, origin=(c.x, c.y))
    scaled_pt = affinity.scale(pt, xfact=xfactor, yfact=1.0, origin=(c.x, c.y))
    return float(scaled_poly.distance(scaled_pt) * 111.32)

def _inat_get(params):
    headers = {
        "Accept": "application/json",
        "User-Agent": "Mijn-Nachtvlinders-Streamlit/0.3"
    }
    r = requests.get(
        "https://api.inaturalist.org/v1/observations",
        params=params,
        headers=headers,
        timeout=30,
    )
    if r.status_code == 429:
        raise RuntimeError("iNaturalist vraagt om langzamer te zoeken (HTTP 429). Probeer het over een minuut opnieuw.")
    r.raise_for_status()
    return r.json()

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_inat_lepidoptera(swlat, swlng, nelat, nelng, d1, d2, research_only, max_records=3000):
    """
    Lichte iNaturalist-ophaalroutine.
    Alleen compacte velden worden bewaard; geen foto's, sounds, annotations, etc.
    Daardoor blijft het geheugenverbruik laag op Streamlit Community Cloud.
    """
    base = {
        "taxon_id": 47157,
        "without_taxon_id": 47224,  # Papilionoidea = dagvlinders; uitsluiten voor nachtvlinders
        "rank": "species",
        "geo": "true",
        "swlat": swlat,
        "swlng": swlng,
        "nelat": nelat,
        "nelng": nelng,
        "d1": d1,
        "d2": d2,
        "per_page": 200,
        "order_by": "observed_on",
        "order": "desc",
    }
    if research_only:
        base["quality_grade"] = "research"

    compact = []
    total = 0
    page = 1

    while len(compact) < max_records:
        data = _inat_get({**base, "page": page})
        if page == 1:
            total = int(data.get("total_results") or 0)

        batch = data.get("results") or []
        if not batch:
            break

        for obs in batch:
            taxon = obs.get("taxon") or {}
            gj = obs.get("geojson") or {}
            coords = gj.get("coordinates") or []
            if taxon.get("rank") != "species" or len(coords) < 2:
                continue
            compact.append({
                "id": obs.get("id"),
                "observed_on": obs.get("observed_on"),
                "taxon_id": taxon.get("id"),
                "taxon_name": taxon.get("name"),
                "common_name": taxon.get("preferred_common_name") or "",
                "lon": coords[0],
                "lat": coords[1],
            })
            if len(compact) >= max_records:
                break

        if len(batch) < 200 or len(compact) >= min(total, max_records):
            break

        page += 1
        time.sleep(1.0)

        # Hard safety guard: never paginate beyond 50 pages.
        if page > 50:
            break

    return compact, total

def target_species_from_inat(results, geom, radius_km, butterflycount_seen):
    rows = []
    seen_norm = {str(x).strip().casefold() for x in butterflycount_seen if pd.notna(x)}

    # Cache distances per coordinate tuple during this run.
    distance_cache = {}

    for obs in results:
        scientific = str(obs.get("taxon_name") or "").strip()
        if not scientific or scientific.casefold() in seen_norm:
            continue

        try:
            lon = float(obs.get("lon"))
            lat = float(obs.get("lat"))
        except Exception:
            continue

        key = (round(lon, 6), round(lat, 6))
        if key not in distance_cache:
            distance_cache[key] = distance_to_area_km(lon, lat, geom)
        dist = distance_cache[key]

        if dist <= 0 or dist > radius_km:
            continue

        rows.append({
            "soort": scientific,
            "common_name": obs.get("common_name") or "",
            "afstand_km": dist,
            "observed_on": pd.to_datetime(obs.get("observed_on"), errors="coerce"),
            "observation_id": obs.get("id"),
            "lat": lat,
            "lon": lon,
        })

    if not rows:
        return pd.DataFrame(columns=[
            "soort", "common_name", "waarnemingen", "afstand_km",
            "laatste_waarneming", "nearest_observation_id", "nearest_lat", "nearest_lon"
        ])

    raw = pd.DataFrame(rows)
    nearest_idx = raw.groupby("soort")["afstand_km"].idxmin()
    nearest = raw.loc[nearest_idx, ["soort", "observation_id", "lat", "lon"]].rename(columns={
        "observation_id": "nearest_observation_id",
        "lat": "nearest_lat",
        "lon": "nearest_lon",
    })
    summary = (
        raw.groupby(["soort", "common_name"], dropna=False)
        .agg(
            waarnemingen=("observation_id", "nunique"),
            afstand_km=("afstand_km", "min"),
            laatste_waarneming=("observed_on", "max"),
        )
        .reset_index()
        .merge(nearest, on="soort", how="left")
        .sort_values(["afstand_km", "waarnemingen"], ascending=[True, False])
    )
    return summary

def load_private_butterflycount_data():
    """Laad optionele vaste exports; uitsluitend bedoeld voor een privé-installatie."""
    data_dir = Path(__file__).with_name("private_data")
    if not data_dir.is_dir():
        return
    for zip_path in sorted(data_dir.glob("*.zip")):
        try:
            df = read_zipped_csv_bytes(zip_path.read_bytes())
            kind = classify_file(df)
            if kind == "occurrences" and st.session_state.occ_df is None:
                st.session_state.occ_df = prep_occ(df)
            elif kind == "samples" and st.session_state.sample_df is None:
                st.session_state.sample_df = prep_samples(df)
        except Exception:
            continue

load_private_butterflycount_data()

tab_area = st.container()
tab_data = st.container()
tab_dashboard = st.container()

with tab_area:
    area_pick, area_new = st.columns([3, 1])
    with area_pick:
        uploaded_geo = st.file_uploader(
            "Selecteer gebied",
            type=["geojson", "json"],
            key="moth_area_upload_v10",
        )
    with area_new:
        st.write("")
        if st.button("➕ Nieuw gebied maken", key="new_moth_area_v10"):
            st.session_state.show_area_creator = not st.session_state.show_area_creator

    if uploaded_geo:
        upload_key = (uploaded_geo.name, uploaded_geo.size)
        if st.session_state.get("last_moth_area_upload") != upload_key:
            try:
                obj = json.loads(uploaded_geo.getvalue().decode("utf-8"))
                features = obj.get("features", []) if obj.get("type") == "FeatureCollection" else [obj]
                first_name = None
                for i, feat in enumerate(features, 1):
                    if feat.get("geometry"):
                        name = (feat.get("properties") or {}).get("name") or f"Gebied {i}"
                        st.session_state.areas[name] = feat["geometry"]
                        first_name = first_name or name
                if first_name:
                    st.session_state.active_area = first_name
                    st.session_state.last_moth_area_upload = upload_key
                    st.rerun()
            except Exception as e:
                st.error(f"GeoJSON kon niet worden geopend: {e}")

    if st.session_state.areas:
        names = list(st.session_state.areas)
        current = st.session_state.active_area if st.session_state.active_area in names else names[0]
        if len(names) > 1:
            chosen = st.selectbox("Actief gebied", names, index=names.index(current))
            if chosen != st.session_state.active_area:
                st.session_state.active_area = chosen
                st.rerun()
        elif st.session_state.active_area:
            st.markdown(
                f'<div class="active-area"><b>Actief gebied:</b> {html.escape(st.session_state.active_area)}</div>',
                unsafe_allow_html=True,
            )

    if st.session_state.show_area_creator:
        with st.container(border=True):
            st.subheader("Nieuw gebied maken")
            area_name = st.text_input("Naam van het gebied", placeholder="Bijvoorbeeld: Mijn tuin")
            center = [52.0, 5.0]
            zoom = 8
            if st.session_state.active_area in st.session_state.areas:
                p = shape(st.session_state.areas[st.session_state.active_area])
                c = p.centroid
                center, zoom = [c.y, c.x], 17

            m = folium.Map(location=center, zoom_start=zoom, tiles="OpenStreetMap", control_scale=True)
            if st.session_state.active_area in st.session_state.areas:
                folium.GeoJson(st.session_state.areas[st.session_state.active_area]).add_to(m)
            Draw(
                export=False,
                draw_options={
                    "polyline": False, "circle": False, "circlemarker": False, "marker": False,
                    "polygon": {"allowIntersection": False, "showArea": True}, "rectangle": True,
                },
                edit_options={"edit": True, "remove": True},
            ).add_to(m)
            state = st_folium(m, height=520, width='stretch', key="moth_area_map_v10")
            drawings = state.get("all_drawings") or []
            newest = drawings[-1].get("geometry") if drawings else None
            if st.button("💾 Gebied gebruiken", type="primary"):
                if not area_name.strip():
                    st.error("Geef het gebied een naam.")
                elif not newest:
                    st.error("Teken eerst een gebied.")
                else:
                    st.session_state.areas[area_name.strip()] = newest
                    st.session_state.active_area = area_name.strip()
                    st.session_state.show_area_creator = False
                    st.rerun()

with tab_data:
    uploads = st.file_uploader(
        "ButterflyCount-bestanden (occurrences en samples)",
        type=["zip"],
        accept_multiple_files=True,
        help="Selecteer de twee ZIP-bestanden uit Moth trap downloads.",
    )

    if uploads:
        data_upload_key = tuple((up.name, up.size) for up in uploads)
        if st.session_state.get("last_moth_data_upload") != data_upload_key:
            for up in uploads:
                try:
                    df = read_zipped_csv(up)
                    kind = classify_file(df)
                    if kind == "occurrences":
                        st.session_state.occ_df = prep_occ(df)
                    elif kind == "samples":
                        st.session_state.sample_df = prep_samples(df)
                    else:
                        st.warning(f"{up.name}: bestandstype niet herkend.")
                except Exception as e:
                    st.error(f"{up.name}: {e}")
            st.session_state.last_moth_data_upload = data_upload_key

    if st.session_state.occ_df is not None:
        occ = st.session_state.occ_df
        st.metric("Occurrence-regels", len(occ))
        st.caption(
            f"{occ['soort'].nunique()} soorten · "
            f"{int(occ['aantal'].sum()):,} individuen"
        )

    if st.session_state.sample_df is not None:
        sam = st.session_state.sample_df
        st.metric("Moth-trap samples", len(sam))
        st.caption(f"{sam['Location'].nunique()} locaties")

with tab_dashboard:
    if st.session_state.active_area not in st.session_state.areas:
        st.info("Kies of teken eerst een gebied.")
        st.stop()

    if st.session_state.occ_df is None or st.session_state.sample_df is None:
        st.info("Upload eerst zowel het occurrences- als samples-bestand.")
        st.stop()

    geom = st.session_state.areas[st.session_state.active_area]
    occ = in_polygon(st.session_state.occ_df, geom)
    sam = in_polygon(st.session_state.sample_df, geom)

    if occ.empty and sam.empty:
        st.warning("Geen moth-trap data gevonden binnen dit gebied.")
        st.stop()

    all_dates = pd.concat(
        [sam["datum"].dropna(), occ["datum"].dropna()],
        ignore_index=True,
    )

    if not all_dates.empty:
        min_date = all_dates.min().date()
        max_date = all_dates.max().date()

        st.markdown("### Periode")
        d1, d2 = st.columns(2)
        with d1:
            start_date = st.date_input(
                "Begindatum",
                value=min_date,
                min_value=min_date,
                max_value=max_date,
            )
        with d2:
            end_date = st.date_input(
                "Einddatum",
                value=max_date,
                min_value=min_date,
                max_value=max_date,
            )

        if start_date > end_date:
            st.error("De begindatum moet vóór of gelijk aan de einddatum liggen.")
            st.stop()

        occ = occ[
            (occ["datum"].dt.date >= start_date)
            & (occ["datum"].dt.date <= end_date)
        ]
        sam = sam[
            (sam["datum"].dt.date >= start_date)
            & (sam["datum"].dt.date <= end_date)
        ]

    overview_options = [
            "Samenvatting",
            "Soorten",
            "Families",
            "Per maand",
            "Per jaar",
            "Vangst per telling",
            "Beste metingen",
            "Heatmap",
            "Nieuwe soorten",
            "Target species",
        ]
    selected_overviews = []
    overview_columns = st.columns(3)
    for index, option in enumerate(overview_options):
        if overview_columns[index % 3].checkbox(
            option,
            value=False,
            key=f"moth_overview_v10_{index}",
        ):
            selected_overviews.append(option)

    if not selected_overviews:
        st.info("Kies hierboven een of meer overzichten.")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tellingen", sam["Sample ID"].nunique())
    c2.metric("Soorten", occ["soort"].nunique())
    c3.metric("Individuen", int(occ["aantal"].sum()))
    c4.metric("Families", occ["familie"].nunique())

    if "Samenvatting" in selected_overviews:
        st.subheader("Samenvatting")
        st.write(
            f"In dit gebied zijn **{sam['Sample ID'].nunique()} moth-trap tellingen** "
            f"met **{occ['soort'].nunique()} soorten** en **{int(occ['aantal'].sum())} individuen**."
        )
        top = (
            occ.groupby(["soort", "familie"])["aantal"]
            .sum().reset_index()
            .sort_values("aantal", ascending=False)
            .head(20)
        )
        st.dataframe(top, width='stretch', hide_index=True)

    if "Soorten" in selected_overviews:
        st.subheader("Meest gevangen soorten")
        sp = (
            occ.groupby("soort")["aantal"].sum()
            .sort_values(ascending=False)
            .head(30)
            .reset_index()
        )
        fig = px.bar(sp, x="soort", y="aantal")
        fig.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig, width='stretch')

    if "Families" in selected_overviews:
        st.subheader("Verdeling over families")
        fam = occ.groupby("familie")["aantal"].sum().sort_values(ascending=False).reset_index()
        fig = px.pie(fam, names="familie", values="aantal", hole=.35)
        st.plotly_chart(fig, width='stretch')

    if "Per maand" in selected_overviews:
        st.subheader("Gemiddeld per kalendermaand")
        monthly = (
            occ.groupby(["jaar", "maand"])
            .agg(individuen=("aantal", "sum"), soorten=("soort", "nunique"))
            .reset_index()
        )
        avg = monthly.groupby("maand")[["individuen", "soorten"]].mean().reset_index()
        names = {1:"Jan",2:"Feb",3:"Mrt",4:"Apr",5:"Mei",6:"Jun",7:"Jul",8:"Aug",9:"Sep",10:"Okt",11:"Nov",12:"Dec"}
        avg["maandnaam"] = avg["maand"].map(names)
        fig = px.bar(avg, x="maandnaam", y=["individuen","soorten"], barmode="group")
        st.plotly_chart(fig, width='stretch')

    if "Per jaar" in selected_overviews:
        st.subheader("Ontwikkeling per jaar")
        yearly = (
            occ.groupby("jaar")
            .agg(individuen=("aantal","sum"), soorten=("soort","nunique"))
            .reset_index()
        )
        fig = px.bar(yearly, x="jaar", y=["individuen","soorten"], barmode="group")
        st.plotly_chart(fig, width='stretch')

    if "Vangst per telling" in selected_overviews:
        st.subheader("Vangst per moth-trap telling")
        by_sample = (
            occ.groupby("Sample ID")
            .agg(individuen=("aantal","sum"), soorten=("soort","nunique"))
            .reset_index()
        )
        merged = sam[["Sample ID","datum","Location"]].merge(by_sample, on="Sample ID", how="left").fillna({"individuen":0,"soorten":0})
        merged = merged.sort_values("datum")
        fig = px.scatter(
            merged, x="datum", y="individuen", size="soorten",
            hover_data=["Location","soorten"]
        )
        st.plotly_chart(fig, width='stretch')
        st.dataframe(merged.sort_values("datum", ascending=False), width='stretch', hide_index=True)

    if "Beste metingen" in selected_overviews:
        st.subheader("Beste metingen")
        st.caption(
            "Metingen staan op aflopend aantal soorten. De paarse balk toont het aantal "
            "soorten; de lijn toont het totale aantal individuen."
        )
        best_counts = (
            occ.groupby("Sample ID")
            .agg(individuen=("aantal", "sum"), soorten=("soort", "nunique"))
            .reset_index()
        )
        sample_details = (
            sam.sort_values("datum")
            .drop_duplicates("Sample ID", keep="last")
            [["Sample ID", "datum", "Location"]]
        )
        best = (
            sample_details.merge(best_counts, on="Sample ID", how="left")
            .fillna({"individuen": 0, "soorten": 0})
            .sort_values(["soorten", "individuen", "datum"], ascending=[False, False, False])
            .reset_index(drop=True)
        )
        best["soorten"] = best["soorten"].astype(int)
        best["individuen"] = best["individuen"].astype(int)
        best["meting"] = (
            best["datum"].dt.strftime("%d-%m-%Y")
            + " · " + best["Location"].fillna("Onbekende locatie").astype(str)
            + " · " + best["Sample ID"].astype(str)
        )

        chart_best = best.head(30).copy()
        fig_best = go.Figure()
        fig_best.add_bar(
            x=chart_best["meting"],
            y=chart_best["soorten"],
            name="Soorten",
            marker_color="#6f42a6",
            hovertemplate="%{x}<br><b>%{y} soorten</b><extra></extra>",
        )
        fig_best.add_scatter(
            x=chart_best["meting"],
            y=chart_best["individuen"],
            name="Individuen",
            mode="lines+markers",
            yaxis="y2",
            line={"color": "#ef6c00", "width": 3},
            hovertemplate="%{x}<br><b>%{y} individuen</b><extra></extra>",
        )
        fig_best.update_layout(
            xaxis={"title": "Meting", "tickangle": -45},
            yaxis={"title": "Aantal soorten", "rangemode": "tozero"},
            yaxis2={
                "title": "Aantal individuen",
                "overlaying": "y",
                "side": "right",
                "rangemode": "tozero",
            },
            legend={"orientation": "h", "y": 1.12},
            margin={"b": 150},
        )
        st.plotly_chart(fig_best, width='stretch')

        best_table = best[["datum", "Location", "soorten", "individuen"]].copy()
        best_table["datum"] = best_table["datum"].dt.strftime("%d-%m-%Y")
        best_table = best_table.rename(columns={
            "datum": "Datum",
            "Location": "Locatie",
            "soorten": "Soorten",
            "individuen": "Individuen",
        })
        st.dataframe(best_table, width='stretch', hide_index=True)

    if "Heatmap" in selected_overviews:
        st.subheader("Meetlocaties in het gebied")
        st.caption(
            "De kaart toont de vaste moth-trap locaties binnen het getekende gebied. "
            "De grootte van de marker geeft aan hoe vaak er in de gekozen periode is gemeten. "
            "Tik op een locatie voor het aantal metingen en de datum van de laatste meting."
        )

        poly = shape(geom)
        minx, miny, maxx, maxy = poly.bounds

        location_summary = (
            sam.dropna(subset=["lat", "lon", "datum"])
            .groupby(["Location", "lat", "lon"], dropna=False)
            .agg(
                metingen=("Sample ID", "nunique"),
                laatste_meting=("datum", "max"),
                eerste_meting=("datum", "min"),
            )
            .reset_index()
            .sort_values(["metingen", "Location"], ascending=[False, True])
        )

        hm = folium.Map(
            location=[poly.centroid.y, poly.centroid.x],
            zoom_start=17,
            tiles="OpenStreetMap",
            control_scale=True,
        )

        folium.GeoJson(
            geom,
            name="Onderzoeksgebied",
            style_function=lambda _: {
                "weight": 3,
                "fillOpacity": 0.06,
            },
        ).add_to(hm)

        if not location_summary.empty:
            max_count = max(int(location_summary["metingen"].max()), 1)

            for _, row in location_summary.iterrows():
                count = int(row["metingen"])
                radius = 7 + 13 * (count / max_count) ** 0.5

                popup_html = (
                    f"<b>{row['Location']}</b><br>"
                    f"Metingen in periode: <b>{count}</b><br>"
                    f"Eerste meting: {row['eerste_meting'].strftime('%d-%m-%Y')}<br>"
                    f"Laatste meting: <b>{row['laatste_meting'].strftime('%d-%m-%Y')}</b>"
                )

                folium.CircleMarker(
                    location=[float(row["lat"]), float(row["lon"])],
                    radius=radius,
                    fill=True,
                    fill_opacity=0.65,
                    weight=2,
                    tooltip=f"{row['Location']} · {count} metingen",
                    popup=folium.Popup(popup_html, max_width=320),
                ).add_to(hm)

            # Zoom exact op het getekende gebied met een kleine marge.
            lat_pad = max((maxy - miny) * 0.08, 0.0005)
            lon_pad = max((maxx - minx) * 0.08, 0.0005)
            hm.fit_bounds([
                [miny - lat_pad, minx - lon_pad],
                [maxy + lat_pad, maxx + lon_pad],
            ])

        st_folium(
            hm,
            height=540,
            width='stretch',
            key="moth_locations_map",
            returned_objects=[],
        )

        if not location_summary.empty:
            table = location_summary.copy()
            table["eerste_meting"] = table["eerste_meting"].dt.strftime("%d-%m-%Y")
            table["laatste_meting"] = table["laatste_meting"].dt.strftime("%d-%m-%Y")
            table = table.rename(columns={
                "Location": "Locatie",
                "metingen": "Aantal metingen",
                "eerste_meting": "Eerste meting",
                "laatste_meting": "Laatste meting",
            })
            st.dataframe(
                table[["Locatie", "Aantal metingen", "Eerste meting", "Laatste meting"]],
                width='stretch',
                hide_index=True,
            )
        else:
            st.info("Geen meetlocaties gevonden binnen dit gebied en deze periode.")

    if "Nieuwe soorten" in selected_overviews:
        st.subheader("Nieuwe soorten door de tijd")
        first = (
            occ.sort_values("datum")
            .drop_duplicates("soort", keep="first")
            [["datum","soort","familie"]]
            .sort_values("datum", ascending=False)
        )
        first["jaar"] = first["datum"].dt.year
        first["kwartaal"] = first["datum"].dt.quarter
        counts = first.groupby(["jaar","kwartaal"]).size().reset_index(name="nieuwe soorten")
        counts["periode"] = counts["jaar"].astype(str) + " Q" + counts["kwartaal"].astype(str)
        st.plotly_chart(px.bar(counts, x="periode", y="nieuwe soorten"), width='stretch')
        st.dataframe(first, width='stretch', hide_index=True)


    if "Target species" in selected_overviews:
        st.subheader("🎯 Target species")
        st.write(
            "Zoek naar **nachtvlinders (Lepidoptera zonder Papilionoidea) die nog niet in jouw ButterflyCount-data "
            "binnen dit gebied voorkomen**, maar die op iNaturalist wel vlak buiten het gebied zijn waargenomen."
        )
        st.caption(
            "De afstand wordt gemeten vanaf de waarneming tot de rand van het getekende gebied, "
            "dus niet vanaf het middelpunt. Standaard wordt 25 km gebruikt."
        )

        s1, s2, s3 = st.columns(3)
        with s1:
            target_radius = st.selectbox(
                "Maximale afstand",
                [5, 10, 25, 50],
                index=2,
                format_func=lambda x: f"{x} km",
            )
        with s2:
            lookback_years = st.selectbox(
                "iNaturalist-periode",
                [1, 3, 5, 10],
                index=1,
                format_func=lambda x: f"afgelopen {x} jaar",
            )
        with s3:
            min_nearby = st.selectbox(
                "Minimaal aantal nabije waarnemingen",
                [1, 2, 3, 5, 10],
                index=2,
            )

        research_only = st.checkbox("Alleen Research Grade iNaturalist-waarnemingen", value=True)
        st.caption(
            "Tip: een minimum van 3 of 5 waarnemingen voorkomt dat één verdwaalde of foutieve melding "
            "meteen als target verschijnt."
        )

        target_key = (
            st.session_state.active_area,
            int(target_radius),
            int(lookback_years),
            int(min_nearby),
            bool(research_only),
        )
        if st.session_state.target_key != target_key:
            bbox = expanded_bbox(geom, target_radius)
            d2_inat = date.today()
            d1_inat = d2_inat - timedelta(days=365 * lookback_years)

            # 'Niet in gebied gezien' baseren we bewust op alle geüploade ButterflyCount-jaren,
            # niet alleen op de momenteel gekozen dashboardperiode.
            all_inside = in_polygon(st.session_state.occ_df, geom)
            seen_species = set(all_inside["soort"].dropna().astype(str))

            with st.spinner("iNaturalist-nachtvlinderwaarnemingen rond het gebied ophalen… Dit kan bij veel waarnemingen even duren."):
                try:
                    results, total = fetch_inat_lepidoptera(
                        round(bbox["swlat"], 6),
                        round(bbox["swlng"], 6),
                        round(bbox["nelat"], 6),
                        round(bbox["nelng"], 6),
                        d1_inat.isoformat(),
                        d2_inat.isoformat(),
                        research_only,
                        3000,
                    )
                    targets = target_species_from_inat(
                        results,
                        geom,
                        float(target_radius),
                        seen_species,
                    )
                    st.session_state.target_df = targets
                    st.session_state.target_meta = {
                        "radius": target_radius,
                        "years": lookback_years,
                        "research_only": research_only,
                        "api_total": total,
                        "downloaded": len(results),
                        "seen_inside": len(seen_species),
                    }
                    st.session_state.selected_targets = []
                    st.session_state.target_key = target_key
                except Exception as e:
                    st.error(f"Target species konden niet worden opgehaald: {e}")

        target_df = st.session_state.target_df
        meta = st.session_state.target_meta or {}

        if target_df is None:
            st.info("De targetsoorten worden automatisch opgehaald.")
        else:
            shown = target_df[target_df["waarnemingen"] >= min_nearby].copy()

            if meta.get("api_total", 0) > meta.get("downloaded", 0):
                st.warning(
                    f"iNaturalist vond {meta['api_total']:,} waarnemingen in het zoekvenster. "
                    f"De app analyseerde maximaal {meta['downloaded']:,} compacte waarnemingen. "
                    "De targetlijst kan daardoor onvolledig zijn; kies eventueel een kortere periode of kleinere afstand."
                )

            m1, m2, m3 = st.columns(3)
            m1.metric("Target-kandidaten", len(shown))
            m2.metric("ButterflyCount-soorten al in gebied", meta.get("seen_inside", 0))
            if not shown.empty:
                m3.metric("Dichtstbijzijnde target", f"{shown['afstand_km'].min():.1f} km")
            else:
                m3.metric("Dichtstbijzijnde target", "—")

            if shown.empty:
                st.info("Geen target species gevonden met deze instellingen.")
            else:
                display = shown.copy()
                display["afstand_km"] = display["afstand_km"].round(1)
                display["laatste_waarneming"] = pd.to_datetime(
                    display["laatste_waarneming"], errors="coerce"
                ).dt.strftime("%d-%m-%Y")

                def target_label(r):
                    common = f" · {r['common_name']}" if r["common_name"] else ""
                    return f"{r['soort']}{common} — {r['afstand_km']:.1f} km ({int(r['waarnemingen'])} waarn.)"

                options = {
                    target_label(r): r["soort"]
                    for _, r in shown.iterrows()
                }
                selected_labels = st.multiselect(
                    "Kies jouw target species",
                    options=list(options.keys()),
                    default=[
                        lab for lab, species in options.items()
                        if species in st.session_state.selected_targets
                    ],
                )
                st.session_state.selected_targets = [options[x] for x in selected_labels]

                table = display[[
                    "soort", "common_name", "afstand_km",
                    "waarnemingen", "laatste_waarneming"
                ]].rename(columns={
                    "soort": "Wetenschappelijke naam",
                    "common_name": "Algemene naam iNaturalist",
                    "afstand_km": "Dichtstbij (km)",
                    "waarnemingen": "Waarnemingen",
                    "laatste_waarneming": "Laatste waarneming",
                })
                st.dataframe(table, width='stretch', hide_index=True)

                st.markdown("#### Kaart target species")
                poly = shape(geom)
                tm = folium.Map(
                    location=[poly.centroid.y, poly.centroid.x],
                    zoom_start=10,
                    tiles="OpenStreetMap",
                    control_scale=True,
                )
                folium.GeoJson(
                    geom,
                    name="Onderzoeksgebied",
                    style_function=lambda _: {"weight": 3, "fillOpacity": 0.08},
                ).add_to(tm)

                map_rows = shown
                if st.session_state.selected_targets:
                    map_rows = shown[
                        shown["soort"].isin(st.session_state.selected_targets)
                    ]

                for _, r in map_rows.head(150).iterrows():
                    common = f"<br>{r['common_name']}" if r["common_name"] else ""
                    obs_url = f"https://www.inaturalist.org/observations/{int(r['nearest_observation_id'])}"
                    popup = (
                        f"<b>{r['soort']}</b>{common}<br>"
                        f"Afstand tot gebied: <b>{r['afstand_km']:.1f} km</b><br>"
                        f"Nabije waarnemingen: {int(r['waarnemingen'])}<br>"
                        f"<a href='{obs_url}' target='_blank'>Open dichtstbijzijnde iNaturalist-waarneming</a>"
                    )
                    folium.CircleMarker(
                        location=[float(r["nearest_lat"]), float(r["nearest_lon"])],
                        radius=7,
                        fill=True,
                        fill_opacity=0.75,
                        weight=2,
                        tooltip=f"{r['soort']} · {r['afstand_km']:.1f} km",
                        popup=folium.Popup(popup, max_width=340),
                    ).add_to(tm)

                bbox_map = expanded_bbox(geom, min(float(target_radius), 25.0))
                tm.fit_bounds([
                    [bbox_map["swlat"], bbox_map["swlng"]],
                    [bbox_map["nelat"], bbox_map["nelng"]],
                ])
                st_folium(
                    tm,
                    height=560,
                    use_container_width=True,
                    key="target_species_map",
                    returned_objects=[],
                )

                if st.session_state.selected_targets:
                    chosen = shown[
                        shown["soort"].isin(st.session_state.selected_targets)
                    ].copy()
                    chosen["afstand_km"] = chosen["afstand_km"].round(1)
                    csv = chosen.to_csv(index=False).encode("utf-8")
                    st.download_button(
                        "⬇️ Geselecteerde target species als CSV",
                        csv,
                        "target_species.csv",
                        "text/csv",
                    )

st.divider()
st.caption(
    "Mijn Nachtvlinders · Publieksversie 1.1 · ButterflyCount/eBMS moth-trap exports · "
    "gegevens worden lokaal in de actieve Streamlit-sessie verwerkt. "
"Target species gebruikt de openbare iNaturalist API."
)

bottom_a, bottom_b = st.columns(2)
if bottom_a.button("ℹ️ Hoe werkt deze app?", key="moth_help_bottom"):
    st.session_state.show_help = not st.session_state.show_help
if bottom_b.button("🔒 Privacy & gegevens", key="moth_privacy_bottom"):
    st.session_state.show_privacy = not st.session_state.show_privacy

if st.session_state.show_help:
    st.info(
        "Kies bovenaan je gebied en upload daarna de occurrences- en samples-ZIP uit "
        "ButterflyCount. Stel de periode in en selecteer een of meer overzichten. "
        "De berekeningen starten direct; targetsoorten worden via iNaturalist opgehaald."
    )

if st.session_state.show_privacy:
    st.info(
        "De geüploade ButterflyCount-bestanden worden alleen in de actieve Streamlit-sessie "
        "verwerkt. De app vraagt niet om een account of wachtwoord. Alleen voor targetsoorten "
        "worden openbare gegevens bij de iNaturalist API opgehaald."
    )
