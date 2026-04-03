import math
from io import BytesIO

import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Steel Connection Studio", layout="wide")

def round_sig(x, n=4):
    try:
        return round(float(x), n)
    except Exception:
        return x

def first_existing(df, candidates):
    colmap = {str(c).strip().lower(): c for c in df.columns}
    for cand in candidates:
        key = str(cand).strip().lower()
        if key in colmap:
            return colmap[key]
    return None

def infer_shapes_columns(df):
    return {
        "shape": first_existing(df, ["AISC_Manual_Label", "Shape", "EDI_Std_Nomenclature", "Section", "Name"]),
        "type": first_existing(df, ["Type", "ShapeType", "shape type"]),
        "d": first_existing(df, ["d", "D"]),
        "bf": first_existing(df, ["bf", "Bf"]),
        "tw": first_existing(df, ["tw", "Tw"]),
        "tf": first_existing(df, ["tf", "Tf"]),
        "zx": first_existing(df, ["Zx", "ZX"]),
        "sx": first_existing(df, ["Sx", "SX"]),
        "ix": first_existing(df, ["Ix", "IX"]),
        "ry": first_existing(df, ["ry", "Ry"]),
        "area": first_existing(df, ["A", "Area"]),
        "t": first_existing(df, ["t", "T"]),
        "od": first_existing(df, ["OD", "od"]),
        "b": first_existing(df, ["B", "b"]),
        "h": first_existing(df, ["H", "h"]),
    }

def normalize_shapes_df(df):
    mapping = infer_shapes_columns(df)
    if mapping["shape"] is None:
        raise ValueError("Could not identify the shape label column.")

    work = pd.DataFrame()
    for target, source in mapping.items():
        if source is not None and source in df.columns:
            work[target] = df[source]

    if "type" not in work.columns:
        work["type"] = work["shape"].astype(str).str.extract(r"^([A-Z]+)", expand=False).fillna("UNKNOWN")

    for c in ["d", "bf", "tw", "tf", "zx", "sx", "ix", "ry", "area", "t", "od", "b", "h"]:
        if c in work.columns:
            work[c] = pd.to_numeric(work[c], errors="coerce")

    work["shape"] = work["shape"].astype(str)
    work["type"] = work["type"].astype(str)
    return work, mapping

def load_shapes_database(uploaded_file):
    name = uploaded_file.name.lower()
    if name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
        work, mapping = normalize_shapes_df(df)
        return work, mapping, "CSV upload"

    excel = pd.ExcelFile(uploaded_file)
    valid_df = None
    valid_sheet = None

    for sheet in excel.sheet_names:
        try:
            df = pd.read_excel(excel, sheet_name=sheet)
            mapping = infer_shapes_columns(df)
            if mapping["shape"] is not None and any(mapping.get(k) is not None for k in ["d", "bf", "tw", "tf", "t", "od"]):
                valid_df = df
                valid_sheet = sheet
                break
        except Exception:
            pass

    if valid_df is None:
        raise ValueError("No valid AISC-like shapes sheet found in the uploaded workbook.")

    work, mapping = normalize_shapes_df(valid_df)
    return work, mapping, valid_sheet

def default_shapes_db():
    data = [
        ["W18X35","W",18.2,6.0,0.300,0.425,75.0,82.0,510.0,1.40,10.3,None,None,None,None],
        ["W21X50","W",20.7,6.54,0.380,0.615,111.0,102.0,1060.0,1.58,14.7,None,None,None,None],
        ["W24X62","W",23.7,7.09,0.430,0.590,144.0,122.0,1450.0,1.67,18.2,None,None,None,None],
        ["W27X84","W",26.7,10.0,0.460,0.670,207.0,169.0,2260.0,2.10,24.7,None,None,None,None],
        ["W30X99","W",29.7,10.5,0.520,0.760,269.0,210.0,3120.0,2.25,29.1,None,None,None,None],
        ["W14X90","W",14.0,14.5,0.440,0.710,169.0,181.0,1270.0,3.38,26.5,None,None,None,None],
        ["HSS10X10X5/8","HSS",10.0,10.0,None,None,54.0,47.0,235.0,3.05,22.3,0.625,None,10.0,10.0],
        ["HSS12X8X1/2","HSS",12.0,8.0,None,None,52.0,46.0,276.0,2.70,18.5,0.500,None,8.0,12.0],
        ["PIPE12STD","PIPE",12.75,None,None,None,34.0,31.0,196.0,2.75,11.9,0.406,12.75,None,None],
    ]
    cols = ["shape","type","d","bf","tw","tf","zx","sx","ix","ry","area","t","od","b","h"]
    return pd.DataFrame(data, columns=cols)

def get_shape_row(df, shape):
    rows = df[df["shape"] == shape]
    return None if rows.empty else rows.iloc[0]

def shapes_by_family(df, family):
    return df[df["type"].astype(str).str.upper().str.contains(family.upper(), na=False)].copy()

def plastic_moment(zx, fy):
    return np.nan if pd.isna(zx) else fy * zx

def probable_moment(zx, fy, ry):
    return np.nan if pd.isna(zx) else ry * fy * zx

def weld_strength_per_inch(fexx, size_in):
    return 0.60 * fexx * 0.707 * size_in

def bolt_shear_nominal(n_bolts, bolt_dia, fub, threads_excluded=True):
    ab = math.pi * bolt_dia**2 / 4.0
    factor = 0.62 if threads_excluded else 0.48
    return n_bolts * factor * fub * ab

def strength_result(nominal, method, phi, omega):
    if pd.isna(nominal):
        return np.nan
    return phi * nominal if method == "LRFD" else nominal / omega

def beam_flange_compactness(row, fy):
    bf = row.get("bf", np.nan)
    tf = row.get("tf", np.nan)
    if pd.isna(bf) or pd.isna(tf) or tf <= 0:
        return np.nan, np.nan, False
    lamb = bf / (2 * tf)
    lamb_p = 0.38 * math.sqrt(29000 / fy)
    return lamb, lamb_p, lamb <= lamb_p

def panel_zone_nominal(col, fy):
    d = col.get("d", np.nan)
    tw = col.get("tw", np.nan)
    if pd.isna(d) or pd.isna(tw):
        return np.nan
    return 0.6 * fy * d * tw

def plate_flexural_nominal(width, thk, fy):
    return fy * width * thk**2 / 4.0

def compute_connection(inp, beam, col):
    method = inp["method"]
    seismic = inp["design_case"] != "Non-seismic"
    Mu = inp["mu_kipft"] * 12.0
    Vu = inp["vu_kip"]
    fyb = inp["fy_beam"]
    fyc = inp["fy_col"]
    conn = inp["connection_family"]
    results = []

    Mp = plastic_moment(beam.get("zx", np.nan), fyb)
    Mpr = probable_moment(beam.get("zx", np.nan), fyb, inp["ry"])
    basis = Mpr if seismic else Mp
    basis_cap = strength_result(basis, method, 0.9, 1.67)
    results.append({
        "Check": "Moment basis",
        "Demand": Mu,
        "Available": basis_cap,
        "Units": "kip-in",
        "Status": "OK" if not pd.isna(basis_cap) and Mu <= basis_cap else "NG",
        "Notes": "Mp for non-seismic, Mpr for seismic."
    })

    lam, lam_p, ok_comp = beam_flange_compactness(beam, fyb)
    results.append({
        "Check": "Beam flange compactness",
        "Demand": lam,
        "Available": lam_p,
        "Units": "-",
        "Status": "OK" if ok_comp else "NG",
        "Notes": "Compactness screen."
    })

    d_beam = float(beam.get("d", 0) or 0)
    tf_beam = float(beam.get("tf", 0) or 0)
    lever_arm = max(d_beam - tf_beam, 1e-6)
    flange_force = Mu / lever_arm

    if conn == "Welded flange + bolted web":
        weld_len = max(float(beam.get("bf", 0) or 0), 1e-6)
        weld_nom = 2 * weld_strength_per_inch(inp["fexx"], inp["flange_weld_size"]) * weld_len
        weld_cap = strength_result(weld_nom, method, 0.75, 2.0)
        results.append({
            "Check": "Flange weld strength",
            "Demand": flange_force,
            "Available": weld_cap,
            "Units": "kip",
            "Status": "OK" if flange_force <= weld_cap else "NG",
            "Notes": "Simplified screening."
        })

        bolt_nom = bolt_shear_nominal(inp["web_bolt_n"], inp["bolt_dia"], inp["bolt_fu"], inp["threads_excluded"])
        bolt_cap = strength_result(bolt_nom, method, 0.75, 2.0)
        results.append({
            "Check": "Web bolt group shear",
            "Demand": Vu,
            "Available": bolt_cap,
            "Units": "kip",
            "Status": "OK" if Vu <= bolt_cap else "NG",
            "Notes": "Simplified web shear check."
        })

    if conn == "Bolted end plate":
        bolt_nom = bolt_shear_nominal(inp["ep_tension_bolts"], inp["bolt_dia"], inp["bolt_fu"], inp["threads_excluded"])
        bolt_cap = strength_result(bolt_nom, method, 0.75, 2.0)
        results.append({
            "Check": "End-plate tension bolt group",
            "Demand": flange_force,
            "Available": bolt_cap,
            "Units": "kip",
            "Status": "OK" if flange_force <= bolt_cap else "NG",
            "Notes": "Proxy for tension-side bolt force."
        })

        ep_nom = plate_flexural_nominal(inp["ep_width"], inp["ep_thk"], fyb)
        ep_cap = strength_result(ep_nom, method, 0.9, 1.67)
        results.append({
            "Check": "End-plate flexure",
            "Demand": Mu,
            "Available": ep_cap,
            "Units": "kip-in",
            "Status": "OK" if Mu <= ep_cap else "NG",
            "Notes": "Screening only."
        })

    if conn == "WUF-W seismic":
        weld_len = max(float(beam.get("bf", 0) or 0), 1e-6)
        weld_nom = 2 * weld_strength_per_inch(inp["fexx"], inp["flange_weld_size"]) * weld_len
        weld_cap = strength_result(weld_nom, method, 0.75, 2.0)
        results.append({
            "Check": "WUF-W flange weld",
            "Demand": flange_force,
            "Available": weld_cap,
            "Units": "kip",
            "Status": "OK" if flange_force <= weld_cap else "NG",
            "Notes": "Prequalified connection screening only."
        })

    if conn == "RBS seismic":
        reduction = max(0.65, 1.0 - 0.25 * inp["rbs_c"])
        zrbs = beam.get("zx", np.nan) * reduction if not pd.isna(beam.get("zx", np.nan)) else np.nan
        mrbs = probable_moment(zrbs, fyb, inp["ry"])
        mrbs_cap = strength_result(mrbs, method, 0.9, 1.67)
        results.append({
            "Check": "RBS reduced section moment",
            "Demand": Mu,
            "Available": mrbs_cap,
            "Units": "kip-in",
            "Status": "OK" if not pd.isna(mrbs_cap) and Mu <= mrbs_cap else "NG",
            "Notes": "Simplified RBS reduction."
        })

    panel_demand = Mu / max(float(col.get("d", 0) or 0) / 2.0 + inp["connection_ecc"], 1e-6)
    panel_nom = panel_zone_nominal(col, fyc)
    panel_cap = strength_result(panel_nom, method, 0.9, 1.5)
    results.append({
        "Check": "Panel zone shear",
        "Demand": panel_demand,
        "Available": panel_cap,
        "Units": "kip",
        "Status": "OK" if not pd.isna(panel_cap) and panel_demand <= panel_cap else "NG",
        "Notes": "Approximate panel zone screening."
    })

    col_m = probable_moment(col.get("zx", np.nan), fyc, inp["ry"])
    beam_m = probable_moment(beam.get("zx", np.nan), fyb, inp["ry"])
    if not pd.isna(col_m) and not pd.isna(beam_m):
        ratio = 2 * col_m / max(beam_m, 1e-6)
        limit = 1.2 if seismic else 1.0
        results.append({
            "Check": "Strong-column / weak-beam ratio",
            "Demand": limit,
            "Available": ratio,
            "Units": "-",
            "Status": "OK" if ratio >= limit else "NG",
            "Notes": "Frame-level concept screen."
        })

    doubler = 0.0
    if not pd.isna(panel_cap) and panel_demand > panel_cap:
        doubler = (panel_demand - panel_cap) / max(0.6 * fyc * float(col.get("d", 1) or 1), 1e-6)

    extras = {
        "flange_force_kip": flange_force,
        "panel_demand_kip": panel_demand,
        "continuity_plate_recommendation": "Likely yes" if not pd.isna(panel_cap) and panel_demand > 0.95 * panel_cap else "Likely no",
        "doubler_plate_thickness_in": doubler,
    }
    return pd.DataFrame(results), extras

def to_excel_bytes(checks_df, beam_row, col_row, inputs, extras):
    out = BytesIO()
    with pd.ExcelWriter(out, engine="xlsxwriter") as writer:
        checks_df.to_excel(writer, index=False, sheet_name="Checks")
        pd.DataFrame([beam_row]).to_excel(writer, index=False, sheet_name="Beam")
        pd.DataFrame([col_row]).to_excel(writer, index=False, sheet_name="Column")
        pd.DataFrame([inputs]).to_excel(writer, index=False, sheet_name="Inputs")
        pd.DataFrame([extras]).to_excel(writer, index=False, sheet_name="Detail")
    out.seek(0)
    return out

st.title("Steel Connection Studio")
st.caption("STAAD + IDEA StatiCa style Streamlit app for steel beam-to-column moment connection screening and concept design")

with st.expander("Important engineering note", expanded=True):
    st.warning("This app is a design aid and concept-level screening tool. Final seismic moment connection design still requires full code checking and engineering judgment.")

st.subheader("1) Section database")
uploaded_shapes = st.file_uploader("Upload AISC shapes database (.xlsx, .xls, .csv)", type=["xlsx", "xls", "csv"])

try:
    if uploaded_shapes is not None:
        shapes_df, detected_map, sheet_used = load_shapes_database(uploaded_shapes)
        st.success(f"Loaded shapes from sheet/source: {sheet_used}")
    else:
        shapes_df = default_shapes_db()
        detected_map = infer_shapes_columns(shapes_df)
        st.info("Using built-in demo shapes. Upload your AISC database for real project work.")
except Exception as e:
    st.error(str(e))
    st.stop()

with st.expander("Detected shape-column mapping"):
    st.json({k: str(v) for k, v in detected_map.items()})

st.sidebar.header("Section filter")
beam_family = st.sidebar.selectbox("Beam family", ["W", "HSS", "PIPE"], index=0)
col_family = st.sidebar.selectbox("Column family", ["W", "HSS", "PIPE"], index=0)

beam_db = shapes_by_family(shapes_df, beam_family)
col_db = shapes_by_family(shapes_df, col_family)

beam_search = st.sidebar.text_input("Search beam section", "")
col_search = st.sidebar.text_input("Search column section", "")

if beam_search:
    beam_db = beam_db[beam_db["shape"].str.contains(beam_search, case=False, na=False)]
if col_search:
    col_db = col_db[col_db["shape"].str.contains(col_search, case=False, na=False)]

if beam_db.empty or col_db.empty:
    st.error("No sections found after filtering.")
    st.stop()

left, right = st.columns([1.05, 1.35])

with left:
    st.subheader("2) Design setup")
    method = st.radio("Design method", ["LRFD", "ASD"], horizontal=True)
    design_case = st.radio("Design category", ["Non-seismic", "Seismic IMF/SMF", "Seismic SMF"], horizontal=True)

    if design_case == "Non-seismic":
        connection_family = st.selectbox("Connection family", ["Welded flange + bolted web", "Bolted end plate"])
    elif design_case == "Seismic IMF/SMF":
        connection_family = st.selectbox("Connection family", ["Bolted end plate", "WUF-W seismic"])
    else:
        connection_family = st.selectbox("Connection family", ["WUF-W seismic", "RBS seismic", "Bolted end plate"])

    beam_shape = st.selectbox("Beam section", beam_db["shape"].tolist())
    col_shape = st.selectbox("Column section", col_db["shape"].tolist())
    beam = get_shape_row(beam_db, beam_shape)
    col = get_shape_row(col_db, col_shape)

    st.markdown("### Material properties")
    c1, c2 = st.columns(2)
    fy_beam = c1.number_input("Beam Fy (ksi)", value=50.0, min_value=36.0)
    fy_col = c2.number_input("Column Fy (ksi)", value=50.0, min_value=36.0)
    c3, c4 = st.columns(2)
    fu_beam = c3.number_input("Beam Fu (ksi)", value=65.0, min_value=50.0)
    fu_col = c4.number_input("Column Fu (ksi)", value=65.0, min_value=50.0)
    c5, c6 = st.columns(2)
    fexx = c5.number_input("Weld electrode Fexx (ksi)", value=70.0, min_value=60.0)
    bolt_fu = c6.number_input("Bolt Fub (ksi)", value=120.0, min_value=58.0)

    st.markdown("### Applied actions")
    d1, d2 = st.columns(2)
    mu_kipft = d1.number_input("Connection moment Mu or Ma (kip-ft)", value=350.0, min_value=0.0)
    vu_kip = d2.number_input("Connection shear Vu or Va (kip)", value=45.0, min_value=0.0)
    connection_ecc = st.number_input("Additional face eccentricity (in)", value=0.0, min_value=0.0)

    st.markdown("### Seismic modifiers")
    ry = st.number_input("Ry factor", value=1.10, min_value=1.0, step=0.01)

    st.markdown("### Fasteners and welds")
    e1, e2 = st.columns(2)
    bolt_dia = e1.number_input("Bolt diameter (in)", value=0.875, min_value=0.5, step=0.125, format="%.3f")
    threads_excluded = e2.checkbox("Threads excluded from shear plane", value=True)
    flange_weld_size = st.number_input("Flange weld size (in)", value=0.375, min_value=0.125, step=0.0625, format="%.4f")
    web_bolt_n = st.number_input("Number of web bolts", value=4, min_value=2, step=1)

    st.markdown("### End-plate inputs")
    ep1, ep2, ep3 = st.columns(3)
    ep_width = ep1.number_input("End-plate width (in)", value=10.0, min_value=4.0)
    ep_thk = ep2.number_input("End-plate thickness (in)", value=0.75, min_value=0.25, step=0.125)
    ep_tension_bolts = ep3.number_input("Tension-side bolts", value=4, min_value=2, step=1)

    st.markdown("### RBS inputs")
    r1, r2, r3 = st.columns(3)
    rbs_a = r1.number_input("RBS a (in)", value=3.0, min_value=0.0)
    rbs_b = r2.number_input("RBS b (in)", value=8.0, min_value=0.0)
    rbs_c = r3.number_input("RBS c ratio", value=0.20, min_value=0.05, max_value=0.5, step=0.01)

    inputs = {
        "method": method,
        "design_case": design_case,
        "connection_family": connection_family,
        "fy_beam": fy_beam,
        "fy_col": fy_col,
        "fu_beam": fu_beam,
        "fu_col": fu_col,
        "fexx": fexx,
        "bolt_fu": bolt_fu,
        "mu_kipft": mu_kipft,
        "vu_kip": vu_kip,
        "connection_ecc": connection_ecc,
        "ry": ry,
        "bolt_dia": bolt_dia,
        "threads_excluded": threads_excluded,
        "flange_weld_size": flange_weld_size,
        "web_bolt_n": web_bolt_n,
        "ep_width": ep_width,
        "ep_thk": ep_thk,
        "ep_tension_bolts": ep_tension_bolts,
        "rbs_a": rbs_a,
        "rbs_b": rbs_b,
        "rbs_c": rbs_c,
    }
    run = st.button("Run design studio", type="primary", use_container_width=True)

with right:
    st.subheader("3) Section browser")
    t1, t2 = st.tabs(["Beam", "Column"])
    with t1:
        st.dataframe(pd.DataFrame([beam]).T.rename(columns={beam.name: beam_shape}), use_container_width=True)
    with t2:
        st.dataframe(pd.DataFrame([col]).T.rename(columns={col.name: col_shape}), use_container_width=True)

    st.subheader("4) Connection concept")
    st.info(f"{connection_family} | {design_case} | {method}")
    st.markdown("**Workflow**")
    st.markdown("1. Load your AISC shapes database.  
2. Filter sections like a STAAD-style browser.  
3. Input demands from STAAD/ETABS/SAP.  
4. Review checks plus continuity/doubler guidance.")

if run:
    checks_df, extras = compute_connection(inputs, beam, col)

    st.subheader("5) Design results")
    util = pd.to_numeric(checks_df["Demand"], errors="coerce") / pd.to_numeric(checks_df["Available"], errors="coerce")
    valid_util = util.dropna()
    max_util = valid_util.max() if not valid_util.empty else np.nan

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Checks OK", int((checks_df["Status"] == "OK").sum()))
    k2.metric("Checks NG", int((checks_df["Status"] == "NG").sum()))
    k3.metric("Max utilization", "-" if pd.isna(max_util) else f"{max_util:.2f}")
    k4.metric("Doubler plate req'd (in)", round_sig(extras["doubler_plate_thickness_in"], 4))

    view = checks_df.copy()
    view["Demand"] = view["Demand"].map(round_sig)
    view["Available"] = view["Available"].map(round_sig)
    st.dataframe(view, use_container_width=True)

    st.markdown("### Governing checks")
    gov = checks_df.copy()
    gov["Utilization"] = util
    gov = gov.sort_values("Utilization", ascending=False)
    st.dataframe(gov[["Check", "Utilization", "Status", "Notes"]], use_container_width=True)

    c1, c2, c3 = st.columns(3)
    c1.info(f"Continuity plate: {extras['continuity_plate_recommendation']}")
    c2.info(f"Doubler plate thickness: {round_sig(extras['doubler_plate_thickness_in'], 4)} in")
    c3.info(f"Flange force: {round_sig(extras['flange_force_kip'], 4)} kip")

    out = to_excel_bytes(checks_df, beam.to_dict(), col.to_dict(), inputs, extras)
    st.download_button(
        "Download Excel report",
        out,
        "steel_connection_studio_results.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
else:
    st.info("Choose the sections and connection setup, then click Run design studio.")
