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
    try:
        print("Subiendo a Drive...")
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
    except Exception as e:
        print("Error en subir_a_drive:", str(e))
        raise

def geodesic_point_buffer(lat, lon, km):
    proj_wgs84 = pyproj.CRS("EPSG:4326")
    proj_aeqd = pyproj.CRS.from_proj4(f"+proj=aeqd +lat_0={lat} +lon_0={lon} +units=m +no_defs")
    project = pyproj.Transformer.from_crs(proj_wgs84, proj_aeqd, always_xy=True).transform
    project_back = pyproj.Transformer.from_crs(proj_aeqd, proj_wgs84, always_xy=True).transform
    buffer = transform(project, Point(lon, lat)).buffer(km * 1000)
    return transform(project_back, buffer), proj_aeqd

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

        # Corregir cálculo de centroides
        gdf_centroides_tmp = gdf_continental.to_crs("EPSG:3857")
        gdf_continental["centroid"] = gdf_centroides_tmp.centroid.to_crs("EPSG:4326")

        geolocator = Nominatim(user_agent="geoapi")
        location = geolocator.geocode(f"{localidad}, {provincia}, Argentina")
        if location is None:
            return jsonify({"error": "Localidad no encontrada"}), 400
        punto_central = Point(location.longitude, location.latitude)

        circle, proj_aeqd = geodesic_point_buffer(location.latitude, location.longitude, radio_km)
        circle_ampliado, _ = geodesic_point_buffer(location.latitude, location.longitude, radio_km + 20)

        gdf_continental["incluido"] = gdf_continental.centroid.within(circle)
        gdf_incluidos = gdf_continental[gdf_continental["incluido"]]
        gdf_intersectan = gdf_continental[gdf_continental.geometry.intersects(circle)]
        gdf_limítrofes = gdf_intersectan[~gdf_intersectan["incluido"]]

        # Proyección a métrico para que se vea como círculo
        gdf_continental_proj = gdf_continental.to_crs(proj_aeqd)
        gdf_incluidos_proj_pg1 = gdf_incluidos.to_crs(proj_aeqd)
        gdf_incluidos_proj_pg2 = gdf_incluidos.to_crs(proj_aeqd)
        gdf_limítrofes_proj = gdf_limítrofes.to_crs(proj_aeqd)
        punto_central_proj = transform(pyproj.Transformer.from_crs("EPSG:4326", proj_aeqd, always_xy=True).transform, punto_central)
        circle_proj_pg1 = transform(pyproj.Transformer.from_crs("EPSG:4326", proj_aeqd, always_xy=True).transform, circle)
        circle_proj_pg2 = circle_proj_pg1

        with PdfPages(output_path) as pdf:
            print("Generando PDF en:", output_path)
            fig1, (ax_mapa, ax_lista) = plt.subplots(1, 2, figsize=(11.69, 8.27), gridspec_kw={'width_ratios': [2, 1]})
            gdf_continental_proj.plot(ax=ax_mapa, edgecolor="black", facecolor="none", linewidth=0.5)
            gdf_incluidos_proj_pg1.plot(ax=ax_mapa, facecolor=color_deseado, edgecolor="black", linewidth=0.5)
            gpd.GeoSeries([circle_proj_pg1]).boundary.plot(ax=ax_mapa, color="blue", linewidth=1)
            ax_mapa.plot(punto_central_proj.x, punto_central_proj.y, "ro", markersize=3)
            minx, miny, maxx, maxy = circle_proj_pg1.bounds
            width = max(maxx - minx, maxy - miny)
            cx, cy = punto_central_proj.x, punto_central_proj.y
            ax_mapa.set_xlim(cx - width / 1.8, cx + width / 1.8)
            ax_mapa.set_ylim(cy - width / 1.8, cy + width / 1.8)
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
            fig1.subplots_adjust(left=0.03, right=0.97, top=0.90, bottom=0.08)
            ax_mapa.set_aspect('equal')
            pdf.savefig(fig1)
            plt.close(fig1)

            fig2, ax_zoom = plt.subplots(figsize=(11.69, 8.27))
            gdf_limítrofes_proj.plot(ax=ax_zoom, facecolor="#DDDDDD", edgecolor="black", linewidth=0.4)
            gdf_incluidos_proj_pg2.plot(ax=ax_zoom, facecolor=color_deseado, edgecolor="black", linewidth=0.6)
            gpd.GeoSeries([circle_proj_pg2]).boundary.plot(ax=ax_zoom, color="blue", linewidth=1)
            ax_zoom.plot(punto_central_proj.x, punto_central_proj.y, marker='o', markersize=5,
                         markerfacecolor='red', markeredgewidth=1, markeredgecolor='white')
            for idx, row in gdf_incluidos_proj_pg2.iterrows():
                ax_zoom.text(row.geometry.centroid.x, row.geometry.centroid.y, row["departamento"], fontsize=6.5, ha="center", va="center", color="black")
            for idx, row in gdf_limítrofes_proj.iterrows():
                ax_zoom.text(row.geometry.centroid.x, row.geometry.centroid.y, row["departamento"], fontsize=5.5, ha="center", va="center", color="#666666")
            minx, miny, maxx, maxy = circle_proj_pg2.bounds
            width = max(maxx - minx, maxy - miny)
            cx, cy = punto_central_proj.x, punto_central_proj.y
            ax_zoom.set_xlim(cx - width / 1.8, cx + width / 1.8)
            ax_zoom.set_ylim(cy - width / 1.8, cy + width / 1.8)
            ax_zoom.set_aspect('equal')
            ax_zoom.axis("off")
            ax_zoom.set_title(f"Zona ampliada desde {localidad}", fontsize=13)
            fig2.subplots_adjust(left=0.03, right=0.97, top=0.90, bottom=0.08)
            ax_zoom.set_aspect('equal')
            pdf.savefig(fig2)
            plt.close(fig2)

        print("Ruta PDF:", output_path)
        print("Nombre PDF:", nombre_final)
        print("Existe el archivo?", os.path.exists(output_path))
        print("Tamaño del archivo:", os.path.getsize(output_path) if os.path.exists(output_path) else "No existe")

        assert os.path.exists(output_path), f"No se generó el PDF en {output_path}"
        print("PDF generado con éxito. Subiendo a Drive...")
        link_pdf = subir_a_drive(output_path, nombre_final)
        print("Enlace generado:", link_pdf)
        return jsonify({"url": link_pdf}), 200

    except Exception as e:
        print("ERROR:", str(e))
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
