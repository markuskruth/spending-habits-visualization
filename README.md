# 3D Map Data Visualization

A Python project for visualizing spending habits of 3 different Indian cities using 3D city maps with building data from OpenStreetMap (OSM). This tool fetches building geometry from OSM, processes it, and generates interactive 3D map visualizations using Pydeck.

## Usage

Install dependencies by:
```bash
pip install -r requirements.txt
```

Run the main script:
```bash
python 3Dmap.py
```

The script will take while to run since it needs to:
1. Fetch building data from OpenStreetMap for specified cities
2. Convert geometries to 3D format with estimated heights
3. Generate interactive HTML visualizations
4. Save results to the `citymaps/` directory

A "map_visualization.html" file is created. Open that file to get the visualization.