from flask import Flask, request, jsonify
from datetime import datetime
import geopandas as gpd
import matplotlib.pyplot as plt
from shapely.geometry import Point
from shapely.ops import transform
import pyproj
from geopy.geocoders import Nominatim
from matplotlib.patches import Rectangle
from matplotlib.backends.backend_pdf import PdfPages
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import os, json

app = Flask(__name__)

FOLDER_ID = '1OsjOeCQn0vM_HWoaDGi6WhJdBaoAIzWT'

def subir_a_drive(ruta_pdf, nombre_pdf):
    json_creds = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])
    creds = service_account.Credentials.from_service_account_info(
        json_creds,
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    service = build("drive", "v3", credentials=creds)
    file_metadata = {"name": nombre_pdf, "parents": [FOLDER_ID]}
    media = MediaFileUpload(ruta_pdf, mimetype="application/pdf")
    file = service.files().create(body=file_metadata, media_body=media, fields="id").execute()
    file_id = file.get("id")
    service.permissions().create(fileId=file_id, body={"type": "anyone", "role": "reader"}).execute()
    return f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"

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

        gdf = gpd.read_file("departamentos-argentina.topojson")
        if gdf.crs is None:
            gdf = gdf.set_crs("EPSG:4326")
        gdf_continental = gdf.cx[-73:-53, -55:-20]
        gdf_continental = gdf_continental[gdf_continental["provincia"] != "CIUDAD AUTONOMA DE BUENOS AIRES"]
        gdf_continental["centroid"] = gdf_continental.centroid

        geolocator = Nominatim(user_agent="geoapi")
        location = geolocator.geocode(f"{localidad}, {provincia}, Argentina")
        if location is None:
            return jsonify({"error": "Localidad no encontrada"}), 400
        punto_central = Point(location.longitude, location.latitude)

        circle = geodesic_point_buffer(location.latitude, location.longitude, radio_km)
        gdf_continental["incluido"] = gdf_continental.centroid.within(circle)
        gdf_incluidos = gdf_continental[gdf_continental["incluido"]]
        circle_ampliado = geodesic_point_buffer(location.latitude, location.longitude, radio_km + 20)
        gdf_intersectan = gdf_continental[gdf_continental.geometry.intersects(circle)]
        gdf_limítrofes = gdf_intersectan[~gdf_intersectan["incluido"]]

        with PdfPages(output_path) as pdf:
            # Página 1: Mapa general + lista
            fig1, (ax_mapa, ax_lista) = plt.subplots(1, 2, figsize=(11.69, 8.27), gridspec_kw={'width_ratios': [2, 1]})
            gdf_continental.plot(ax=ax_mapa, edgecolor="black", facecolor="none", linewidth=0.5)
            gdf_incluidos.plot(ax=ax_mapa, facecolor=color_deseado, edgecolor="black", linewidth=0.5)
            gpd.GeoSeries([circle], crs="EPSG:4326").boundary.plot(ax=ax_mapa, color="blue", linewidth=1)
            ax_mapa.plot(punto_central.x, punto_central.y, "ro", markersize=3)
            ax_mapa.set_aspect('equal')
            ax_mapa.axis("off")
            ax_mapa.set_title("Mapa general de Argentina", fontsize=10)

            ax_lista.axis("off")
            ax_lista.text(0.5, 0.95, "Departamentos incluidos", ha="center", va="top", fontsize=9, fontweight='bold')
            incluidos = gdf_incluidos["departamento"].sort_values().tolist()
            for i, dpto in enumerate(incluidos):
                y = 0.90 - i * 0.03
                if y < 0.05:
                    ax_lista.text(0.05, y, "…", fontsize=7, ha="left", va="top")
                    break
                ax_lista.text(0.05, y, f"• {dpto}", fontsize=6.5, ha="left", va="top")

            plt.tight_layout()
            plt.suptitle(f"Análisis geográfico desde {localidad}", fontsize=13, y=1.02, fontweight="bold")
            pdf.savefig(fig1)
            plt.close(fig1)

            # Página 2: Zoom
            fig2, ax_zoom = plt.subplots(figsize=(11.69, 8.27))
            gdf_limítrofes.plot(ax=ax_zoom, facecolor="#DDDDDD", edgecolor="black", linewidth=0.4)
            gdf_incluidos.plot(ax=ax_zoom, facecolor=color_deseado, edgecolor="black", linewidth=0.6)
            gpd.GeoSeries([circle], crs="EPSG:4326").boundary.plot(ax=ax_zoom, color="blue", linewidth=1)
            ax_zoom.plot(punto_central.x, punto_central.y, marker='o', markersize=5,
                         markerfacecolor='red', markeredgewidth=1, markeredgecolor='white')
            for idx, row in gdf_incluidos.iterrows():
                pt = row["centroid"]
                ax_zoom.text(pt.x, pt.y, row["departamento"], fontsize=6.5, ha="center", va="center", color="black")
            for idx, row in gdf_limítrofes.iterrows():
                pt = row["centroid"]
                ax_zoom.text(pt.x, pt.y, row["departamento"], fontsize=5.5, ha="center", va="center", color="#666666")
            ax_zoom.set_xlim(circle.bounds[0], circle.bounds[2])
            ax_zoom.set_ylim(circle.bounds[1], circle.bounds[3])
            ax_zoom.set_aspect('equal')
            ax_zoom.axis("off")
            ax_zoom.set_title(f"Zona ampliada desde {localidad}", fontsize=13)
            plt.tight_layout()
            pdf.savefig(fig2)
            plt.close(fig2)

        link_pdf = subir_a_drive(output_path, nombre_final)
        return jsonify({"url": link_pdf}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
