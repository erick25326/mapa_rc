from flask import Flask, request, jsonify
from datetime import datetime
import os

app = Flask(__name__)

@app.route("/", methods=["POST"])
def generar_mapa():
    data = request.get_json()
    localidad = data.get("localidad")
    provincia = data.get("provincia")
    radio = float(data.get("radio"))
    color = data.get("color")
    nombre = data.get("nombre")
    fecha = datetime.today().strftime("%Y-%m-%d")
    nombre_final = f"mapa_{nombre}_{fecha}.pdf"

    # Acá iría tu código de generación de mapa usando geopandas
# 🔧 Instalar dependencias
!pip install geopandas adjustText geopy shapely pyproj

# 📚 Importar librerías
import geopandas as gpd
import matplotlib.pyplot as plt
from shapely.geometry import Point
from shapely.ops import transform
import pyproj
from geopy.geocoders import Nominatim
from matplotlib.patches import Rectangle
import math

# 🗂️ Montar Google Drive y cargar el archivo
from google.colab import drive
drive.mount('/content/drive')

# 📁 Leer TopoJSON desde Drive
gdf = gpd.read_file("/content/drive/MyDrive/departamentos-argentina.topojson")

# 🧭 CRS y filtrado
if gdf.crs is None:
    gdf = gdf.set_crs("EPSG:4326")
gdf_continental = gdf.cx[-73:-53, -55:-20]
gdf_continental = gdf_continental[gdf_continental["provincia"] != "CIUDAD AUTONOMA DE BUENOS AIRES"]
gdf_continental["centroid"] = gdf_continental.centroid

# 🎯 Parámetros de entrada
localidad = "Pergamino, Buenos Aires"
radio_km = 100
color_deseado = "#FF5733"

# 🌍 Geolocalizar localidad
geolocator = Nominatim(user_agent="geoapi")
location = geolocator.geocode(f"{localidad}, Argentina")
if location is None:
    raise ValueError("No se pudo geolocalizar la localidad.")
punto_central = Point(location.longitude, location.latitude)

# 🔵 Crear círculo geodésico
def geodesic_point_buffer(lat, lon, km):
    proj_wgs84 = pyproj.Proj(init='epsg:4326')
    aeqd_proj = pyproj.Proj(proj='aeqd', lat_0=lat, lon_0=lon)
    project = pyproj.Transformer.from_proj(proj_wgs84, aeqd_proj).transform
    project_back = pyproj.Transformer.from_proj(aeqd_proj, proj_wgs84).transform
    buffer = transform(project, Point(lon, lat)).buffer(km * 1000)
    return transform(project_back, buffer)

circle = geodesic_point_buffer(location.latitude, location.longitude, radio_km)

# 📌 Marcar departamentos incluidos
gdf_continental["incluido"] = gdf_continental.centroid.within(circle)
gdf_incluidos = gdf_continental[gdf_continental["incluido"]]

# 🖼️ Crear figura horizontal A4 con 3 columnas
fig, (ax_mapa, ax_lista, ax_zoom) = plt.subplots(1, 3, figsize=(11.69, 8.27), gridspec_kw={'width_ratios': [3, 1.5, 3]})

# --- MAPA GENERAL (sin etiquetas) ---
gdf_continental.plot(ax=ax_mapa, edgecolor="black", facecolor="none", linewidth=0.5)
gdf_incluidos.plot(ax=ax_mapa, facecolor=color_deseado, edgecolor="black", linewidth=0.5)
gpd.GeoSeries([circle], crs="EPSG:4326").boundary.plot(ax=ax_mapa, color="blue", linewidth=1)
ax_mapa.plot(punto_central.x, punto_central.y, "ro", markersize=3)
ax_mapa.set_facecolor("white")
ax_mapa.axis("off")
ax_mapa.set_xlim([-73, -53])
ax_mapa.set_ylim([-55, -20])
ax_mapa.set_title("Mapa general", fontsize=10)

# --- LISTA DE DEPARTAMENTOS ---
ax_lista.axis("off")
ax_lista.set_facecolor("white")
ax_lista.add_patch(Rectangle((0, 0), 1, 1, transform=ax_lista.transAxes,
                             facecolor='white', edgecolor='lightgray', linewidth=1))
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

# --- ZOOM DE LA ZONA ---

# 1. Ampliar el círculo para contexto visual (más grande)
circle_ampliado = geodesic_point_buffer(location.latitude, location.longitude, radio_km + 20)

# 2. Filtrar departamentos que INTERSECTAN con el círculo original
gdf_intersectan = gdf_continental[gdf_continental.geometry.intersects(circle)]

# 3. Limítrofes: intersectan pero NO están totalmente dentro
gdf_limítrofes = gdf_intersectan[~gdf_intersectan["incluido"]]

# 4. Mostrar los limítrofes en gris claro
gdf_limítrofes.plot(ax=ax_zoom, facecolor="#DDDDDD", edgecolor="black", linewidth=0.4)

# 5. Mostrar los incluidos en color principal
gdf_incluidos.plot(ax=ax_zoom, facecolor=color_deseado, edgecolor="black", linewidth=0.6)

# 6. Dibujar el círculo original
gpd.GeoSeries([circle], crs="EPSG:4326").boundary.plot(ax=ax_zoom, color="blue", linewidth=1)

# 7. Punto central con borde blanco
ax_zoom.plot(punto_central.x, punto_central.y, marker='o', markersize=5,
             markerfacecolor='red', markeredgewidth=1, markeredgecolor='white')

# 8. Etiquetas de incluidos (en negro)
for idx, row in gdf_incluidos.iterrows():
    pt = row["centroid"]
    nombre = row["departamento"]
    ax_zoom.text(pt.x, pt.y, nombre, fontsize=6.5, ha="center", va="center", color="black")

# 9. Etiquetas de limítrofes (en gris oscuro)
for idx, row in gdf_limítrofes.iterrows():
    pt = row["centroid"]
    nombre = row["departamento"]
    ax_zoom.text(pt.x, pt.y, nombre, fontsize=5.5, ha="center", va="center", color="#666666")

# 10. Ajustes visuales finales (sin título ni leyenda)
ax_zoom.set_facecolor("white")
ax_zoom.axis("off")
ax_zoom.set_xlim(circle.bounds[0], circle.bounds[2])
ax_zoom.set_ylim(circle.bounds[1], circle.bounds[3])


# 📌 Título general arriba
plt.suptitle(f"Análisis geográfico desde {localidad}", fontsize=13, y=1.08, fontweight="bold")

# 💾 Exportar
plt.subplots_adjust(top=0.90)
plt.tight_layout()
plt.savefig("mapa_departamentos_zoom_horizontal.pdf", dpi=150, bbox_inches="tight")
plt.show()


    # y guardar como:
    path = f"/tmp/{nombre_final}"
    with open(path, "w") as f:
        f.write("Simulando mapa generado")

    url_simulada = f"https://example.com/{nombre_final}"  # Reemplazar con URL real o subir a Drive

    return jsonify({"url": url_simulada})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
