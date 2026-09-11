from datetime import date
import io
import json
import zipfile

import folium
import pandas as pd
import plotly.express as px
import streamlit as st
from folium.plugins import Draw, HeatMap
from shapely.geometry import Point, shape
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
@media (max-width: 768px) {
  .block-container {padding-left: .8rem; padding-right: .8rem;}
}
</style>
""", unsafe_allow_html=True)

st.markdown('<span class="release-badge">Prototype v0.1 · Moth traps</span>', unsafe_allow_html=True)
st.title("🦋 Mijn Nachtvlinders")
st.caption(
    "Analyseer moth-trap tellingen uit ButterflyCount/eBMS binnen je eigen getekende gebied."
)

if "areas" not in st.session_state:
    st.session_state.areas = {}
if "active_area" not in st.session_state:
    st.session_state.active_area = None
if "occ_df" not in st.session_state:
    st.session_state.occ_df = None
if "sample_df" not in st.session_state:
    st.session_state.sample_df = None

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

def read_zipped_csv(upload):
    data = upload.getvalue()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        csvs = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if not csvs:
            raise ValueError("Geen CSV-bestand gevonden in ZIP.")
        with z.open(csvs[0]) as f:
            return pd.read_csv(f)

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

tab_area, tab_data, tab_dashboard = st.tabs(["🗺️ Gebied", "📥 Data", "📊 Dashboard"])

with tab_area:
    st.subheader("Onderzoeksgebied")

    if st.session_state.areas:
        names = list(st.session_state.areas)
        current = st.session_state.active_area if st.session_state.active_area in names else None
        idx = names.index(current) + 1 if current else 0
        chosen = st.selectbox("Opgeslagen gebieden", ["— kies —"] + names, index=idx)
        if chosen != "— kies —" and st.button("📂 Gebied openen", type="primary"):
            st.session_state.active_area = chosen
            st.rerun()

    uploaded_geo = st.file_uploader("Open opgeslagen GeoJSON", type=["geojson", "json"])
    if uploaded_geo:
        try:
            obj = json.loads(uploaded_geo.getvalue().decode("utf-8"))
            features = obj.get("features", []) if obj.get("type") == "FeatureCollection" else [obj]
            for i, feat in enumerate(features, 1):
                if feat.get("geometry"):
                    name = (feat.get("properties") or {}).get("name") or f"Gebied {i}"
                    st.session_state.areas[name] = feat["geometry"]
                    st.session_state.active_area = name
            st.success("Gebied(en) ingelezen.")
        except Exception as e:
            st.error(f"GeoJSON kon niet worden geopend: {e}")

    area_name = st.text_input("Naam nieuw gebied", placeholder="Bijvoorbeeld: Mijn tuin")

    center = [52.0, 5.0]
    zoom = 8
    if st.session_state.active_area in st.session_state.areas:
        p = shape(st.session_state.areas[st.session_state.active_area])
        c = p.centroid
        center, zoom = [c.y, c.x], 15

    m = folium.Map(location=center, zoom_start=zoom, tiles="OpenStreetMap", control_scale=True)
    if st.session_state.active_area in st.session_state.areas:
        folium.GeoJson(st.session_state.areas[st.session_state.active_area]).add_to(m)

    Draw(
        export=False,
        draw_options={
            "polyline": False, "circle": False, "circlemarker": False, "marker": False,
            "polygon": {"allowIntersection": False, "showArea": True},
            "rectangle": True,
        },
        edit_options={"edit": True, "remove": True},
    ).add_to(m)

    state = st_folium(m, height=540, use_container_width=True, key="moth_area_map")
    drawings = state.get("all_drawings") or []
    newest = drawings[-1].get("geometry") if drawings else None

    if st.button("💾 Gebied bewaren"):
        if not area_name.strip():
            st.error("Geef het gebied een naam.")
        elif not newest:
            st.error("Teken eerst een gebied.")
        else:
            st.session_state.areas[area_name.strip()] = newest
            st.session_state.active_area = area_name.strip()
            st.success("Gebied bewaard voor deze sessie.")

    if st.session_state.areas:
        export = json.dumps({
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "properties": {"name": n}, "geometry": g}
                for n, g in st.session_state.areas.items()
            ]
        }, ensure_ascii=False, indent=2)

        st.download_button(
            "⬇️ Gebieden opslaan als GeoJSON",
            export,
            "mijn_nachtvlindergebieden.geojson",
            "application/geo+json",
        )

with tab_data:
    st.subheader("ButterflyCount moth-trap data")
    st.write(
        "Upload de twee ZIP-bestanden uit **Moth trap downloads**: "
        "**occurrences** en **samples**. De app herkent automatisch welk bestand welk type is."
    )

    uploads = st.file_uploader(
        "Upload moth-trap ZIP-bestanden",
        type=["zip"],
        accept_multiple_files=True,
    )

    if uploads:
        for up in uploads:
            try:
                df = read_zipped_csv(up)
                kind = classify_file(df)
                if kind == "occurrences":
                    st.session_state.occ_df = prep_occ(df)
                    st.success(f"Occurrences geladen: {len(df):,} regels")
                elif kind == "samples":
                    st.session_state.sample_df = prep_samples(df)
                    st.success(f"Samples geladen: {len(df):,} tellingen")
                else:
                    st.warning(f"{up.name}: bestandstype niet herkend.")
            except Exception as e:
                st.error(f"{up.name}: {e}")

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

    years = sorted(set(sam["jaar"].dropna().astype(int).tolist()) | set(occ["jaar"].dropna().astype(int).tolist()))
    if years:
        year_range = st.slider(
            "Periode",
            min_value=min(years),
            max_value=max(years),
            value=(min(years), max(years)),
        )
        occ = occ[(occ["jaar"] >= year_range[0]) & (occ["jaar"] <= year_range[1])]
        sam = sam[(sam["jaar"] >= year_range[0]) & (sam["jaar"] <= year_range[1])]

    overview = st.selectbox(
        "Kies overzicht",
        [
            "Samenvatting",
            "Soorten",
            "Families",
            "Per maand",
            "Per jaar",
            "Vangst per telling",
            "Heatmap",
            "Nieuwe soorten",
        ]
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tellingen", sam["Sample ID"].nunique())
    c2.metric("Soorten", occ["soort"].nunique())
    c3.metric("Individuen", int(occ["aantal"].sum()))
    c4.metric("Families", occ["familie"].nunique())

    if overview == "Samenvatting":
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
        st.dataframe(top, use_container_width=True, hide_index=True)

    elif overview == "Soorten":
        st.subheader("Meest gevangen soorten")
        sp = (
            occ.groupby("soort")["aantal"].sum()
            .sort_values(ascending=False)
            .head(30)
            .reset_index()
        )
        fig = px.bar(sp, x="soort", y="aantal")
        fig.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)

    elif overview == "Families":
        st.subheader("Verdeling over families")
        fam = occ.groupby("familie")["aantal"].sum().sort_values(ascending=False).reset_index()
        fig = px.pie(fam, names="familie", values="aantal", hole=.35)
        st.plotly_chart(fig, use_container_width=True)

    elif overview == "Per maand":
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
        st.plotly_chart(fig, use_container_width=True)

    elif overview == "Per jaar":
        st.subheader("Ontwikkeling per jaar")
        yearly = (
            occ.groupby("jaar")
            .agg(individuen=("aantal","sum"), soorten=("soort","nunique"))
            .reset_index()
        )
        fig = px.bar(yearly, x="jaar", y=["individuen","soorten"], barmode="group")
        st.plotly_chart(fig, use_container_width=True)

    elif overview == "Vangst per telling":
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
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(merged.sort_values("datum", ascending=False), use_container_width=True, hide_index=True)

    elif overview == "Heatmap":
        st.subheader("Heatmap van tellingen")
        poly = shape(geom)
        c = poly.centroid
        hm = folium.Map(location=[c.y,c.x], zoom_start=13, tiles="OpenStreetMap")
        folium.GeoJson(geom).add_to(hm)
        heat = sam.dropna(subset=["lat","lon"])[["lat","lon"]].values.tolist()
        if heat:
            HeatMap(heat, radius=18, blur=14).add_to(hm)
        st_folium(hm, height=520, use_container_width=True, key="moth_heat")

    elif overview == "Nieuwe soorten":
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
        st.plotly_chart(px.bar(counts, x="periode", y="nieuwe soorten"), use_container_width=True)
        st.dataframe(first, use_container_width=True, hide_index=True)

st.divider()
st.caption(
    "Mijn Nachtvlinders v0.1 · ButterflyCount/eBMS moth-trap exports · "
    "gegevens worden lokaal in de actieve Streamlit-sessie verwerkt."
)
