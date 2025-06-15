import streamlit as st
import geopandas as gpd 
import folium
from streamlit_folium import st_folium
import json
from config import Config
from models import create_llm
from langchain.prompts import PromptTemplate
from langchain.output_parsers import PydanticOutputParser
from langchain.chains import LLMChain
from pydantic import BaseModel, Field
from typing import Optional, List
import os
import pycountry
import time

# ------------------------
# Setup
# ------------------------
llm = create_llm(Config.MODEL)

# ------------------------
# 1. Pydantic Models
# ------------------------

class GeoQueryItem(BaseModel):
    area_name: str = Field(..., description="Target area, such as country, region, city.")
    admin_level: int = Field(..., description="OSM admin level: 2 for countries, 4 for regions, 6 for departments, 8 for cities, 9 for arrondissements/districts.")
    is_group_query: bool = Field(..., description="Whether the query is about a region group like EU or GCC.")
    group_name: Optional[str] = Field(None, description="If a group query, the group name.")
    parent_country: Optional[str] = Field(None, description="If area_name is not a country, specify the parent country.")

class GeoQueryList(BaseModel):
    queries: List[GeoQueryItem]

parser = PydanticOutputParser(pydantic_object=GeoQueryList)

# ------------------------
# 2. Prompt Template
# ------------------------

parser = PydanticOutputParser(pydantic_object=GeoQueryList)

prompt_template = PromptTemplate(
    template="""
You are a geospatial assistant that understands natural language and converts it into structured metadata for each place mentioned.

For each location mentioned in the query, extract the following structured metadata:
- **area_name**: name of the city, region, or country
- **admin_level**:
  - 2 for countries
  - 4 for regions, emirates, or first-level administrative divisions
  - 6 for departments, governorates, or municipalities
  - 8 for cities or towns
  - 9 for districts, arrondissements, neighborhoods, or sub-city localities
- **is_group_query**: true if the query mentions a group (e.g., "EU countries", "GCC countries")
- **group_name**: optional name of the group (e.g., "GCC")
- **parent_country**: if the area is not a country, specify its parent country

### Special handling for **GCC countries**:
- If the query mentions any of the following **GCC countries**: "United Arab Emirates", "Saudi Arabia", "Qatar", "Oman", "Kuwait", or "Bahrain", apply:
  - **Level 0**: country itself → admin_level = 4
  - **Level 1**: emirates (UAE), provinces/governorates (others) → admin_level = 5
  - **Level 2**: municipalities, wilayats, zones → admin_level = 6
  - **Level 3**: districts, neighborhoods → admin_level = 9

For example:
- "Dubai" or "Abu Dhabi" → admin_level = 4, parent_country = "United Arab Emirates"
- "districts of Riyadh" → Riyadh → admin_level = 9, parent_country = "Saudi Arabia"

### For other countries:
- Apply standard interpretation based on keywords in the query (e.g., "regions", "departments", "cities", "districts") and assign the corresponding admin_level.
- If multiple places are listed, apply the correct admin_level based on their context or the keyword used.

Return your response as a JSON object with the key `"queries"` containing a list of extracted locations:

```json
{{
  "queries": [
    {{
      "area_name": "Riyadh",
      "admin_level": 4,
      "is_group_query": false,
      "group_name": null,
      "parent_country": "Saudi Arabia"
    }},
    {{
      "area_name": "Al Malaz",
      "admin_level": 9,
      "is_group_query": false,
      "group_name": null,
      "parent_country": "Saudi Arabia"
    }}
  ]
}}
Examples:
Example 1:
Query: "Show me emirates of UAE"

{{
  "queries": [
    {{
      "area_name": "United Arab Emirates",
      "admin_level": 5,
      "is_group_query": false,
      "group_name": null,
      "parent_country": null
    }}
  ]
}}
Example 2:
Query: "Show me districts of Dubai"

{{
  "queries": [
    {{
      "area_name": "Dubai",
      "admin_level": 9,
      "is_group_query": false,
      "group_name": null,
      "parent_country": "United Arab Emirates"
    }}
  ]
}}
Example 3:
Query: "Show me provinces of Saudi Arabia and cities in France"

{{
  "queries": [
    {{
      "area_name": "Saudi Arabia",
      "admin_level": 4,
      "is_group_query": false,
      "group_name": null,
      "parent_country": null
    }},
    {{
      "area_name": "France",
      "admin_level": 8,
      "is_group_query": false,
      "group_name": null,
      "parent_country": null
    }}
  ]
}}
Now analyze the following:

{format_instructions}

User query: {query}
""",
input_variables=["query"],
partial_variables={"format_instructions": parser.get_format_instructions()}
)
# ------------------------
# 3. LangChain Chain
# ------------------------
llm = create_llm(Config.MODEL)
chain = LLMChain(llm=llm, prompt=prompt_template)

# ------------------------
# Utility Functions (same as in your original code, copy them verbatim)
# ------------------------
# Include: resolve_group, country_to_iso3, load_from_geojson, load_from_shapefile,
# get_data, select_name_field, extract_geometry_with_name, combine_geojsons

# ------------------------
# 4. Helper Functions
# ------------------------
# Define alias mappings globally or load from a file
group_aliases = {
    "eu": "European Union",
    "european union": "European Union",
    "gcc": "GCC",
    "gulf cooperation council": "GCC",
    "saarc": "South Asia",
    "south asia": "South Asia",
    "na": "North America",
    "north america": "North America",
    "sa": "South America",
    "south america": "South America",
    "asia": "Asia",
    "africa": "Africa",
    "oceania": "Oceania",
    "world": "World"
}

def resolve_group(group_name: str, groups_path="./geodata/groups.json") -> List[str]:
    group_name_clean = group_name.strip().lower()

    # Normalize using alias mapping
    canonical_name = group_aliases.get(group_name_clean, group_name)

    # Load the group dictionary
    with open(groups_path) as f:
        groups = json.load(f)

    # Return the matched countries list or empty list
    return groups.get(canonical_name, [])

def country_to_iso3(name: str) -> str:
    try:
        return pycountry.countries.lookup(name).alpha_3
    except LookupError:
        raise ValueError(f"Could not resolve country name: {name}")

def load_from_geojson(file_path: str, countries: List[str]) -> dict:
    gdf = gpd.read_file(file_path)
    gdf = gdf[gdf.geometry.type.isin(["Polygon", "MultiPolygon"])]
    # Determine which column has country names
    country_col = None
    for col in ["name", "country", "admin", "NAME", "CNTRY_NAME"]:
        if col in gdf.columns:
            country_col = col
            break
    if country_col is None:
        raise ValueError("No country name column found in GeoDataFrame!")
    # Filter for EU countries
    gdf_eu = gdf[gdf[country_col].isin(countries)]
    return gdf_eu


def load_from_shapefile(
    country_iso3: str,
    admin_level: int,
    area_name: Optional[str] = None,
    base_path: str = "./geodata/countries"
) -> dict:
    print(area_name)
    country_iso3 = country_iso3.upper()
    found_level = None
    gdf = None

    # Fallback search from requested level down to 0
    for level in range(admin_level, -1, -1):
        shp_path = os.path.join(base_path, country_iso3, f"{country_iso3.lower()}_{level}.shp")
        if os.path.exists(shp_path):
            print(f"Loading shapefile from admin level {level}: {shp_path}")
            gdf = gpd.read_file(shp_path)
            found_level = level
            break

    if gdf is None:
        raise FileNotFoundError(f"No shapefile found for {country_iso3} from admin level {admin_level} down to 0.")

    # Try these columns in order for name matching
    name_columns = ["COUNTRY", "NAME_0", "NAME_1", "NAME_2", "NAME_3", "NAME_4", "NAME_5"]

    if area_name:
        area_name_lower = area_name.lower()
        for col in name_columns:
            if col in gdf.columns:
                filtered = gdf[gdf[col].str.lower() == area_name_lower]
                if not filtered.empty:
                    return filtered
        raise ValueError(f"No data found for '{area_name}' in any of {name_columns} at admin level {found_level}")
    else:
        return gdf

 
def get_data(parsed: GeoQueryItem) -> dict:
    if parsed.is_group_query:
        countries = resolve_group(parsed.group_name)
        print(countries)
        return load_from_geojson("./geodata/level1.json", countries)

    elif parsed.admin_level == 2:
        # Country-level: load country polygons for given area_name
        return load_from_geojson("./geodata/level1.json", [parsed.area_name])

    else:
        try:
            iso = country_to_iso3(parsed.parent_country or parsed.area_name)
            print(iso)
        except ValueError as e:
            raise ValueError(f"Failed to resolve country for shapefile lookup: {e}")

        # For admin levels other than 2, treat as "all areas" if area_name is None or a general phrase
        # Here we assume if area_name is exactly the country name or empty, load all subdivisions
        # Otherwise, filter by area_name if provided and specific
        general_admin_levels = {4, 6, 8, 9}
        
        if parsed.admin_level in general_admin_levels and (
            parsed.area_name is None or (
                parsed.parent_country and parsed.area_name.lower() == parsed.parent_country.lower()
            )
        ):
            return load_from_shapefile(iso, parsed.admin_level)
        
        # Else filter by area_name
        return load_from_shapefile(iso, parsed.admin_level, area_name=parsed.area_name)


def select_name_field(gdf: gpd.GeoDataFrame, admin_level: int) -> str:
    """
    Select the best name field based on admin_level and existing columns in the GeoDataFrame.
    """
    # Likely columns based on admin level
    admin_name_map = {
        9: ["NAME_4", "NAME_3", "name"],
        8: ["NAME_4", "NAME_3", "name"],
        7: ["NAME_3", "NAME_2", "NAME_1", "name"],
        6: ["NAME_2", "NAME_1", "name"],
        4: ["NAME_1", "COUNTRY", "name"],
        2: ["COUNTRY", "NAME", "name"],
    }

    # Fallback list if admin level is unknown
    default_candidates = ["NAME_4", "NAME_3", "NAME_2", "NAME_1", "COUNTRY", "NAME", "name", "admin", "label"]

    # Get candidates from mapping or default
    candidates = admin_name_map.get(admin_level, default_candidates)

    for col in candidates:
        if col in gdf.columns and gdf[col].dropna().astype(str).str.strip().any():
            return col

    raise ValueError(f"No suitable name field found for admin_level={admin_level}")

def extract_geometry_with_name(gdf: gpd.GeoDataFrame, name_column: str) -> gpd.GeoDataFrame:
    if name_column not in gdf.columns:
        raise ValueError(f"Column '{name_column}' not found in DataFrame")
    
    return gdf[[name_column, "geometry"]].rename(columns={name_column: "name"}).copy()

def combine_geojsons(geojson_list):
    all_features = []
    for gj in geojson_list:
        if gj.get("type") == "FeatureCollection":
            all_features.extend(gj.get("features", []))
        elif gj.get("type") == "Feature":
            all_features.append(gj)  # Support individual Feature objects
        else:
            raise ValueError(f"Unsupported GeoJSON type: {gj.get('type')}")

    return {
        "type": "FeatureCollection",
        "features": all_features
    }



@st.cache_data(show_spinner=False)
def create_map(geojson):
    m = folium.Map(location=[20, 10], zoom_start=2)
    folium.GeoJson(
        geojson,
        name="Labeled Areas",
        tooltip=folium.GeoJsonTooltip(fields=["name"], aliases=["Name:"])
    ).add_to(m)
    folium.LayerControl().add_to(m)
    return m

def save_map_html(m, filename="map.html"):
    m.save(filename)

# ------------------------
# Streamlit UI
# ------------------------
st.set_page_config(layout="wide")
st.title("🗺️ GeoBoundary Extractor")

query = st.text_input("Enter your query", value="show me districts of Paris, Lyon, Marseille")
if st.button("Run Query") and query:
    with st.spinner("Processing..."):
        try:
            start_time = time.time()
            result = chain.invoke({"query": query})
            invoke_time = time.time() - start_time
            st.success(f"LLM chain.invoke() executed in {invoke_time:.2f} seconds")

            parsed = parser.parse(result["text"])

            geoJson_List = []
            for q in parsed.queries:
                try:
                    start_gdf_time = time.time()
                    gdf = get_data(q)
                    gdf_time = time.time() - start_gdf_time
                    st.info(f"get_data() for {q.area_name} executed in {gdf_time:.2f} seconds")

                    field_name = select_name_field(gdf, q.admin_level)
                    new_gdf = extract_geometry_with_name(gdf, field_name)
                    geojson_dict = new_gdf.__geo_interface__
                    geoJson_List.append(geojson_dict)
                except Exception as e:
                    st.warning(f"Failed to process {q.area_name}: {e}")

            combined = combine_geojsons(geoJson_List)

            m = create_map(combined)

            # Save to HTML file and display
            map_file = "temp_map.html"
            save_map_html(m, map_file)

            # Display the saved HTML file inside Streamlit
            with open(map_file, 'r', encoding='utf-8') as f:
                html_data = f.read()
            st.components.v1.html(html_data, height=600, scrolling=True)

            # Optionally clean up the file after display (uncomment if desired)
            # os.remove(map_file)

        except Exception as e:
            st.error(f"Error: {e}")