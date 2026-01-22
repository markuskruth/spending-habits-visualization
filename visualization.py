import pandas as pd
import pydeck as pdk
import osmnx as ox
import numpy as np
import pickle, json, os


def convert_building_data(buildings, simplify_tol=0.00005):
    """
    Convert geometry data to the format PyDeck expects
    """
    buildings_data = []
    for idx, row in buildings.iterrows():
        geom = row.geometry
        geom = geom.simplify(simplify_tol)
        
        # Estimate building height based on tags
        height = estimate_building_height(row)
        
        if geom.geom_type == "Polygon":
            coords = [list(geom.exterior.coords)]
            buildings_data.append({"coordinates": coords, "height": height})
        elif geom.geom_type == "MultiPolygon":
            for poly in geom.geoms:
                coords = [list(poly.exterior.coords)]
                buildings_data.append({"coordinates": coords, "height": height})
    return buildings_data


def estimate_building_height(building):
    """
    Estimate building height based on OSM tags
    Returns height in meters
    """
    # Check if explicit height is available
    if "height" in building and pd.notna(building["height"]):
        try:
            height_str = str(building["height"])
            # Remove 'm' or other units and convert to float
            height = float(height_str.replace("m", "").replace("ft", "").strip())
            return height if height > 0 else 15
        except:
            pass
    
    # Check building levels
    if "building:levels" in building and pd.notna(building["building:levels"]):
        try:
            levels = float(building["building:levels"])
            return levels * 3.5  # Assume 3.5m per level
        except:
            pass
    
    # Estimate based on building type
    building_type = building.get("building", "yes")
    
    # High buildings
    if building_type in ["commercial", "office", "retail", "hotel", "apartments"]:
        return np.random.uniform(20, 40)
    
    # Medium buildings
    elif building_type in ["industrial", "warehouse", "school", "hospital", "public"]:
        return np.random.uniform(10, 20)
    
    # Low buildings
    elif building_type in ["house", "residential", "detached", "terrace", "bungalow"]:
        return np.random.uniform(5, 12)
    
    # Very low buildings
    elif building_type in ["garage", "shed", "cabin", "hut", "roof"]:
        return np.random.uniform(3, 6)
    
    # Religious/civic buildings
    elif building_type in ["church", "cathedral", "mosque", "temple", "shrine"]:
        return np.random.uniform(15, 30)
    
    # Default: generic building
    else:
        return np.random.uniform(8, 18)


def get_buildings_data(city_names, load):
    if not load:
        buildings_data = []
        save_rate = 10
        for i, city in enumerate(city_names):
            print(f"({i+1}/{len(city_names)}), City: {city}")
            try:
                buildings = ox.features_from_place(city, tags={"building": True})
                converted_data = convert_building_data(buildings)
                buildings_data.append(converted_data)
            except Exception as e:
                print(f"Did not find data for city: {city}: {e}")
            
            if i % save_rate == 0:
                with open("buildings_data1.pkl", "wb") as f:
                    pickle.dump(buildings_data, f)
                print("Saved to file")
            
        with open("buildings_data1.pkl", "wb") as f:
            pickle.dump(buildings_data, f)
        print("Saved to file")
    else:
        with open("buildings_data1.pkl", "rb") as f:
            buildings_data = pickle.load(f)
        
        city_building_pairs = list(zip(city_names, buildings_data))
        city_building_pairs.sort(key=lambda x: len(x[1]), reverse=True)
        city_names, buildings_data = zip(*city_building_pairs)
        city_names, buildings_data = list(city_names), list(buildings_data)
        print("Loaded building data")
    
    return buildings_data


def calculate_spending_by_category_and_quarter(df, city_names, quarters):
    """
    Calculate spending for all cities, categories, and yealry quarters
    Returns two dicts: 
    spending_data: {quarter: {category: {city: spending}}}
    percentage_data: {quarter: {category: {city: percentage}}}
    """
    print("Calculating spending data for all quarters and categories")
    spending_data = {}
    percentage_data = {}
    
    for quarter in quarters:
        spending_data[quarter] = {}
        percentage_data[quarter] = {}
        
        # Filter data by quarter
        if quarter == "All Time":
            quarter_df = df
        else:
            quarter_df = df[df["YearQuarter"] == quarter]
        
        total_spending = {}
        
        # Calculate total spending per city for this quarter
        for city_name in city_names:
            city_data = quarter_df[quarter_df["City"] == city_name]
            total_spending[city_name] = float(city_data["Amount"].sum())
        
        # Calculate for "All Categories"
        spending_data[quarter]["All Categories"] = {}
        percentage_data[quarter]["All Categories"] = {}
        for city_name in city_names:
            spending_data[quarter]["All Categories"][city_name] = total_spending[city_name]
            percentage_data[quarter]["All Categories"][city_name] = 100.0
        
        # Calculate for each individual category
        for category in df["Exp Type"].unique():
            spending_data[quarter][category] = {}
            percentage_data[quarter][category] = {}
            for city_name in city_names:
                city_data = quarter_df[(quarter_df["City"] == city_name) & (quarter_df["Exp Type"] == category)]
                spending = float(city_data["Amount"].sum())
                spending_data[quarter][category][city_name] = spending
                
                # Calculate percentage of total spending
                percentage_data[quarter][category][city_name] = (spending / total_spending[city_name]) * 100
    
    return spending_data, percentage_data


def get_heatmap_color(percentage, min_percentage, max_percentage):    
    normalized = (percentage - min_percentage) / (max_percentage - min_percentage)
    
    # Color gradient: blue, green, yellow, orange, red
    if normalized < 0.25:
        r = 0
        g = int(normalized * 4 * 255) + 200
        b = 200
    elif normalized < 0.5:
        r = 0
        g = 255
        b = int((0.5 - normalized) * 4 * 255)
    elif normalized < 0.75:
        r = int((normalized - 0.5) * 4 * 255)
        g = 255
        b = 0
    else:
        r = 255
        g = int((1 - normalized) * 4 * 255)
        b = 0
    
    return [r, g, b]


def create_citymap(building_data, lat, lon, zoom, color):
    """
    Create a PyDeck 3D map with specified heatmap color
    """

    layer = pdk.Layer(
        "PolygonLayer",
        data=building_data,
        get_polygon="coordinates",
        get_fill_color=color,
        get_line_color=[50, 50, 50],
        stroked=True,
        filled=True,
        extruded=True,
        wireframe=True,
        get_elevation="height",
        elevation_scale=1,
        opacity=0.8,
        line_width_min_pixels=1,
    )
    view_state = pdk.ViewState(
        latitude=lat, 
        longitude=lon, 
        zoom=zoom, 
        pitch=45,  # Angle the camera for 3D view
        bearing=0
    )
    deck = pdk.Deck(layers=[layer], initial_view_state=view_state)
    return deck.to_html(as_string=True)


def get_city_coords(city_names):
    # Get city coordinates
    num_cities_to_show = len(city_names)
    city_coords = []

    for i, (city_name, city_buildings) in enumerate(zip(city_names, buildings_data[:num_cities_to_show])):
        try:
            gdf = ox.geocode_to_gdf(city_name)
            lat = float(gdf.centroid.y.values[0])
            lon = float(gdf.centroid.x.values[0])
            if city_name == "Ahmedabad, India":
                lat = 23.021537
                lon = 72.580057
            elif city_name == "Delhi, India":
                lat = 28.6448
                lon = 77.2164

        except Exception as e:
            print(f"Could not get coordinates for {city_name}: {e}")
            lat, lon = 0.0, 0.0

        city_buildings_subset = city_buildings[:min(len(city_buildings)-1, 20000)]
        city_coords.append({
            "name": city_name,
            "lat": lat,
            "lon": lon,
            "buildings": city_buildings_subset,
            "index": i
        })
    return city_coords


def generate_citymaps(quarters, categories, percentage_data, city_coords, spending_data):
    """
    Generate maps for each quarter, category, and city combination
    """
    print("\nGenerating maps for all quarter-category-city combinations")
    map_files = {}  # {quarter: {category: {city_index: filename}}}
    scale_ranges = {}  # {quarter: {category: {min, max}}}

    for quarter in quarters:
        map_files[quarter] = {}
        scale_ranges[quarter] = {}
        
        for category in categories:
            map_files[quarter][category] = {}
            
            # Get percentage values for this quarter and category
            category_percentages = percentage_data[quarter][category]
            percentage_values = [category_percentages[city["name"]] for city in city_coords]
            
            # Calculate average and set min/max to average +- 1.0%
            avg_percentage = sum(percentage_values) / len(percentage_values)
            min_percentage = avg_percentage - 1.0
            max_percentage = avg_percentage + 1.0
            
            # Use actual min/max values if more extreme
            min_percentage = min(min(percentage_values), min_percentage)
            max_percentage = max(max(percentage_values), max_percentage)
            
            # Store scale range
            scale_ranges[quarter][category] = {"min": min_percentage, "max": max_percentage}
            
            for city_info in city_coords:
                city_idx = city_info["index"]
                city_name = city_info["name"]
                
                # Get color based on percentage of total spending
                percentage = category_percentages[city_name]
                color = get_heatmap_color(percentage, min_percentage, max_percentage)
                
                # Create map
                html_code = create_citymap(
                    city_info["buildings"], 
                    city_info["lat"], 
                    city_info["lon"], 
                    zoom=12, 
                    color=color
                )
                
                # Save with unique filename
                safe_quarter = quarter.replace(" ", "_")
                safe_category = category.replace(" ", "_").replace("/", "-")
                map_filename = f"citymaps/map_q_{safe_quarter}_city_{city_idx}_cat_{safe_category}.html"
                with open(map_filename, "w", encoding="utf-8") as f:
                    f.write(html_code)
                
                map_files[quarter][category][city_idx] = map_filename
    
    return scale_ranges, map_files


if __name__ == "__main__":
    # Read in data and preprocess
    df = pd.read_csv("data/data.csv")
    df.drop(columns=["Card Type"], inplace=True)
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True)

    # Add Quarter column
    df["Year"] = df["Date"].dt.year
    df["Quarter"] = df["Date"].dt.quarter
    df["YearQuarter"] = df["Year"].astype(str) + "-Q" + df["Quarter"].astype(str)

    city_names = ["Bengaluru, India", "Delhi, India", "Ahmedabad, India"]
    load = True
    buildings_data = get_buildings_data(city_names, load)

    
    # Get all unique categories and quarters
    categories = ["All Categories"] + sorted(df["Exp Type"].unique().tolist())
    quarters = ["All Time"] + sorted(df["YearQuarter"].unique().tolist())

    # Calculate all spending data
    spending_data, percentage_data = calculate_spending_by_category_and_quarter(df, city_names, quarters)

    # Create citymaps directory if it doesn't exist
    os.makedirs("citymaps", exist_ok=True)

    city_coords = get_city_coords(city_names)

    scale_ranges, map_files = generate_citymaps(quarters, categories, percentage_data, city_coords, spending_data)


    ################################################################
    # AI has been used to create the upcoming HTML part of this code
    ################################################################
    
    # Create main interactive HTML file
    html = """
    <!DOCTYPE html>
    <html>
    <head>
    <style>
    body { 
        background: #f0f0f0; 
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
        margin: 0; 
        padding: 20px; 
    }
    h2 { 
        text-align: center; 
        color: #333; 
        margin-bottom: 10px;
    }
    .controls { 
        text-align: center; 
        margin: 20px auto; 
        padding: 20px; 
        background: white; 
        border-radius: 8px; 
        max-width: 700px; 
        box-shadow: 0 2px 4px rgba(0,0,0,0.1); 
    }
    .control-group {
        display: inline-block;
        margin: 10px 15px;
    }
    .controls label {
        font-weight: bold;
        color: #555;
        margin-right: 10px;
        display: inline-block;
    }
    .controls select {
        padding: 8px 15px;
        font-size: 14px;
        border: 2px solid #ddd;
        border-radius: 5px;
        background: white;
        cursor: pointer;
        min-width: 200px;
    }
    .controls select:hover {
        border-color: #999;
    }
    .legend { 
        text-align: center; 
        margin: 20px auto; 
        padding: 15px; 
        background: white; 
        border-radius: 8px; 
        max-width: 600px; 
        box-shadow: 0 2px 4px rgba(0,0,0,0.1); 
    }
    .legend-gradient { 
        height: 30px; 
        background: linear-gradient(to right, rgb(0,200,200), rgb(0,255,255), rgb(0,255,0), rgb(255,255,0), rgb(255,0,0)); 
        border-radius: 4px; 
        margin: 10px 0; 
    }
    .legend-labels { 
        display: flex; 
        justify-content: space-between; 
        font-size: 12px; 
        color: #666; 
    }
    .map-container { 
        display: flex; 
        flex-wrap: wrap; 
        justify-content: center; 
        gap: 20px; 
    }
    .map-box { 
        width: 32%; 
        min-width: 350px; 
        height: 500px; 
        background: white; 
        border: 1px solid #ccc; 
        border-radius: 8px; 
        overflow: hidden; 
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        transition: transform 0.2s;
    }
    .map-box:hover {
        transform: translateY(-5px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.15);
    }
    .map-box h3 { 
        text-align: center; 
        margin: 15px 0 5px 0; 
        color: #555; 
    }
    .spending-info { 
        text-align: center; 
        font-size: 14px; 
        margin: 5px 0 10px 0;
        font-weight: bold;
        padding: 8px;
        border-radius: 4px;
        transition: all 0.3s ease;
        min-height: 45px;
    }
    iframe { 
        width: 100%; 
        height: calc(100% - 100px); 
        border: none; 
    }
    .loading {
        text-align: center;
        color: #999;
        font-style: italic;
    }
    </style>
    </head>
    <body>
    <h2>Indian Cities Spending Habits</h2>

    <div class="controls">
        <div class="control-group">
            <label for="quarterSelect">Time Period:</label>
            <select id="quarterSelect" onchange="updateHeatmap()">
    """

    # Add quarter options
    for quarter in quarters:
        html += f'            <option value="{quarter}">{quarter}</option>\n'

    html += """
            </select>
        </div>
        <div class="control-group">
            <label for="categorySelect">Category:</label>
            <select id="categorySelect" onchange="updateHeatmap()">
    """

    # Add category options
    for category in categories:
        html += f'            <option value="{category}">{category}</option>\n'

    html += """
            </select>
        </div>
    </div>

    <div class="legend">
        <strong>Spending Intensity</strong>
        <div class="legend-gradient"></div>
        <div class="legend-labels">
            <span id="minSpending">Low</span>
            <span id="maxSpending">High</span>
        </div>
    </div>

    <div class="map-container">
    """

    # Add map boxes
    for city_info in city_coords:
        html += f"""
        <div class='map-box'>
            <h3>{city_info['name']}</h3>
            <div class='spending-info' id='spending-{city_info['index']}'>
                Spending: $0
            </div>
            <iframe src='' id='map-{city_info['index']}' class='loading'>Loading...</iframe>
        </div>
    """

    html += """
    </div>

    <script>
    // Spending data for all quarters, categories and cities
    const spendingData = """ + json.dumps(spending_data, indent=2) + """;

    // Percentage data for all quarters, categories and cities
    const percentageData = """ + json.dumps(percentage_data, indent=2) + """;

    // Scale ranges for all quarters and categories
    const scaleRanges = """ + json.dumps(scale_ranges, indent=2) + """;

    // Map files for all quarters, categories and cities
    const mapFiles = """ + json.dumps(map_files, indent=2) + """;

    const cityNames = """ + json.dumps([c['name'] for c in city_coords]) + """;
    const cityIndices = """ + json.dumps([c['index'] for c in city_coords]) + """;

    function getHeatmapColor(intensity, minIntensity, maxIntensity) {
        let normalized;
        if (maxIntensity === minIntensity) {
            normalized = 0.5;
        } else {
            normalized = (intensity - minIntensity) / (maxIntensity - minIntensity);
        }
        
        let r, g, b;
        if (normalized < 0.25) {
            r = 0;
            g = Math.floor(normalized * 4 * 255) + 200;
            b = 200;
        } else if (normalized < 0.5) {
            r = 0;
            g = 255;
            b = Math.floor((0.5 - normalized) * 4 * 255);
        } else if (normalized < 0.75) {
            r = Math.floor((normalized - 0.5) * 4 * 255);
            g = 255;
            b = 0;
        } else {
            r = 255;
            g = Math.floor((1 - normalized) * 4 * 255);
            b = 0;
        }
        
        return [r, g, b];
    }

    function updateHeatmap() {
        const quarter = document.getElementById('quarterSelect').value;
        const category = document.getElementById('categorySelect').value;
        const categoryData = spendingData[quarter][category];
        const categoryPercentages = percentageData[quarter][category];
        const categoryMaps = mapFiles[quarter][category];
        
        // Get min and max percentage for this quarter and category
        const { min: minPercentage, max: maxPercentage } = scaleRanges[quarter][category];

        // Update legend to show percentages
        document.getElementById('minSpending').textContent = `Low (${minPercentage.toFixed(1)}%)`;
        document.getElementById('maxSpending').textContent = `High (${maxPercentage.toFixed(1)}%)`;
        
        // Update each city
        cityIndices.forEach((cityIdx) => {
            const cityName = cityNames[cityIdx];
            const spending = categoryData[cityName];
            const percentage = categoryPercentages[cityName];
            const color = getHeatmapColor(percentage, minPercentage, maxPercentage);
            const rgbString = `rgb(${color[0]}, ${color[1]}, ${color[2]})`;
            
            // Update spending display with both amount and percentage
            const spendingDiv = document.getElementById(`spending-${cityIdx}`);
            spendingDiv.innerHTML = `<strong>$${spending.toLocaleString('en-US', {maximumFractionDigits: 2})}</strong><br><span style="font-size: 12px;">${percentage.toFixed(1)}% of total</span>`;
            spendingDiv.style.color = rgbString;
            spendingDiv.style.backgroundColor = `rgba(${color[0]}, ${color[1]}, ${color[2]}, 0.1)`;
            
            // Update map by changing iframe src
            const iframe = document.getElementById(`map-${cityIdx}`);
            const newSrc = categoryMaps[cityIdx];
            if (iframe.src !== newSrc) {
                iframe.src = newSrc;
            }
        });
    }

    // Initialize with first quarter and category
    window.addEventListener('load', () => {
        updateHeatmap();
    });
    </script>
    </body>
    </html>
    """

    with open("map_visualization.html", "w", encoding="utf-8") as f:
        f.write(html)

    print("\nCreated map_visualization.html")