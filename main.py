from flask import Flask, request, jsonify
from datetime import datetime
import geopandas as gpd
import matplotlib.pyplot as plt
from shapely.geometry import Point
from shapely.ops import transform
import pyproj
from geopy.geocoders import Nominatim
from matplotlib.patches import Rectangle

app = Flask(__name__)

def geodesic_point_buffer(lat, lon, km):
    proj_wgs84 = pyproj.Proj("epsg:4326")
    aeqd_proj = pyproj.Proj(proj='aeqd', lat_0=lat, lon_0=lon)
    project = pyproj.Transformer.from_proj(proj_wgs84, aeqd_proj).transform
    project_back = pyproj.Transformer.from_proj(aeqd_proj, proj_wgs84).transform
    buffer = transform(project, Point(lon, lat)).buffer(km * 1000)
    return transform(project_back, buffer)

@app.route("/", methods=["POST"])
def generar_mapa():
    try:
        data = request.get_json()
        localidad = data.get("localidad")
        provincia = data.get("provincia")
        radio_km = float(data.get("radio"))
        color_deseado = data.get("color")
        nombre = data.get("nombre")

        fecha = datetime.today().strftime("%Y-%m-%d")
        nombre_final = f"mapa_{nombre}_{fecha}.pdf"
        output_path = f"/tmp/{nombre_final}"

        # Cargar TopoJSON (asegurate de tener este archivo en el repo o accesible desde URL)
        gdf = gpd.read_file("departamentos-argentina.topojson")

        if gdf.crs is None:
            gdf = gdf.set_crs("EPSG:4326")

        gdf_continental = gdf.cx[-73:-53, -55:-20]
        gdf_continental = gdf_continental[gdf_continental["provincia"] != "CIUDAD AUTONOMA DE BUENOS AIRES"]
        gdf_continental["centroid"] = gdf_continental.centroid

        # Geolocalizar localidad
        geolocator = Nominatim(user_agent="geoapi")
        location = geolocator.geocode(f"{localidad}, {provincia}, Argentina")
        if location is None:
            return jsonify({"error": "Localidad no encontrada"}), 400
        punto_central = Point(location.longitude, location.latitude)

        circle = geodesic_point_buffer(location.latitude, location.longitude, radio_km)
        gdf_continental["incluido"] = gdf_continental.centroid.within(circle)
        gdf_incluidos = gdf_continental[gdf_continental["incluido"]]

        fig, (ax_mapa, ax_lista, ax_zoom) = plt.subplots(1, 3, figsize=(11.69, 8.27), gridspec_kw={'width_ratios': [3, 1.5, 3]})

        # Mapa general
        gdf_continental.plot(ax=ax_mapa, edgecolor="black", facecolor="none", linewidth=0.5)
        gdf_incluidos.plot(ax=ax_mapa, facecolor=color_deseado, edgecolor="black", linewidth=0.5)
        gpd.GeoSeries([circle], crs="EPSG:4326").boundary.plot(ax=ax_mapa, color="blue", linewidth=1)
        ax_mapa.plot(punto_central.x, punto_central.y, "ro", markersize=3)
        ax_mapa.axis("off")
        ax_mapa.set_title("Mapa general", fontsize=10)

        # Lista de departamentos
        ax_lista.axis("off")
        ax_lista.text(0.5, 0.95, "Departamentos incluidos", ha="center", va="top", fontsize=9, fontweight='bold')
        incluidos = gdf_incluidos["departamento"].sort_values().tolist()
        line_spacing = 0.03
        start_y = 0.90
        for i, dpto in enumerate(incluidos):
            y = start_y - i * line_spacing
            if y < 0.05:
                ax_lista.text(0.05, y, "…", fontsize=7, ha="left", va="top")
                break
            ax_lista.text(0.05, y, f"• {dpto}", fontsize=6.5, ha="left", va="top")

        # Zona ampliada
        circle_ampliado = geodesic_point_buffer(location.latitude, location.longitude, radio_km + 20)
        gdf_intersectan = gdf_continental[gdf_continental.geometry.intersects(circle)]
        gdf_limítrofes = gdf_intersectan[~gdf_intersectan["incluido"]]
        gdf_limítrofes.plot(ax=ax_zoom, facecolor="#DDDDDD", edgecolor="black", linewidth=0.4)
        gdf_incluidos.plot(ax=ax_zoom, facecolor=color_deseado, edgecolor="black", linewidth=0.6)
        gpd.GeoSeries([circle], crs="EPSG:4326").boundary.plot(ax=ax_zoom, color="blue", linewidth=1)
        ax_zoom.plot(punto_central.x, punto_central.y, marker='o', markersize=5, markerfacecolor='red', markeredgewidth=1, markeredgecolor='white')
        for idx, row in gdf_incluidos.iterrows():
            pt = row["centroid"]
            ax_zoom.text(pt.x, pt.y, row["departamento"], fontsize=6.5, ha="center", va="center", color="black")
        for idx, row in gdf_limítrofes.iterrows():
            pt = row["centroid"]
            ax_zoom.text(pt.x, pt.y, row["departamento"], fontsize=5.5, ha="center", va="center", color="#666666")
        ax_zoom.axis("off")
        ax_zoom.set_xlim(circle.bounds[0], circle.bounds[2])
        ax_zoom.set_ylim(circle.bounds[1], circle.bounds[3])

        plt.suptitle(f"Análisis geográfico desde {localidad}", fontsize=13, y=1.08, fontweight="bold")
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches="tight")

        # 🔁 En una versión futura: subir a Drive o Dropbox y devolver URL real
        return jsonify({"url": f"GENERADO: {nombre_final} (ver en /tmp)"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
