# Steel Connection Studio

A Streamlit app inspired by a STAAD-style section browser and an IDEA StatiCa-style connection workflow.

Included:
- LRFD and ASD
- Non-seismic, Seismic IMF/SMF, and Seismic SMF
- Connection families: welded flange + bolted web, bolted end plate, WUF-W seismic, RBS seismic
- Auto-detect correct AISC sheet from uploaded Excel database
- Searchable W / HSS / PIPE filters
- Panel zone, compactness, strong-column / weak-beam, weld, bolt, and concept plate checks
- Continuity plate and doubler plate recommendation
- Excel export

Run:
pip install -r requirements.txt
streamlit run app.py