from flask import Flask, request, jsonify
from datetime import datetime
import geopandas as gpd
import matplotlib.pyplot as plt
from shapely.geometry import Point
from shapely.ops import transform
import pyproj
import requests
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
    proj_aeqd = pyproj.CRS.from_proj4(f"+proj=aeqd +lat_0={lat} +lon_0={lon} +units=m +ellps=WGS84 +no_defs")
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
        radio_km = data.get("radio")
        color_deseado = data.get("color")
        nombre = data.get("nombre")

        if not all([localidad, provincia, radio_km, color_deseado, nombre]):
            return jsonify({"error": "Faltan datos obligatorios"}), 400

        radio_km = float(radio_km)
        fecha = datetime.today().strftime("%Y-%m-%d")
        nombre_final = f"mapa_{nombre}_{fecha}.pdf"
        output_path = f"/tmp/{nombre_final}"

        gdf = gpd.read_file("departamentos-argentina.topojson")
        if gdf.crs is None:
            gdf = gdf.set_crs("EPSG:4326")
        gdf_continental = gdf.cx[-73:-53, -55:-20]
        gdf_continental = gdf_continental[gdf_continental["provincia"] != "CIUDAD AUTONOMA DE BUENOS AIRES"]

        gdf_centroides_tmp = gdf_continental.to_crs("EPSG:3857")
        gdf_continental["centroid"] = gdf_centroides_tmp.centroid.to_crs("EPSG:4326")

        api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
        if not api_key:
            return jsonify({"error": "API Key de Google Maps no configurada"}), 500

        direccion = f"{localidad}, {provincia}, Argentina"
        url_geo = f"https://maps.googleapis.com/maps/api/geocode/json?address={direccion}&key={api_key}"
        response = requests.get(url_geo)
        if response.status_code != 200:
            return jsonify({"error": "Error al consultar Google Maps"}), 500

        data_geo = response.json()
        if data_geo["status"] != "OK":
            return jsonify({"error": f"No se pudo geolocalizar: {data_geo['status']}"}), 400

        location_data = data_geo["results"][0]["geometry"]["location"]
        lat = location_data["lat"]
        lon = location_data["lng"]
        punto_central = Point(lon, lat)

        circle, proj_aeqd = geodesic_point_buffer(lat, lon, radio_km)
        circle_ampliado, _ = geodesic_point_buffer(lat, lon, radio_km + 20)

        gdf_continental["incluido"] = gdf_continental.centroid.within(circle)
        gdf_incluidos = gdf_continental[gdf_continental["incluido"]]
        gdf_intersectan = gdf_continental[gdf_continental.geometry.intersects(circle)]
        gdf_limítrofes = gdf_intersectan[~gdf_intersectan["incluido"]]

        gdf_continental_proj = gdf_continental.to_crs("EPSG:3857")
        gdf_incluidos_proj_pg1 = gdf_incluidos.to_crs("EPSG:3857")
        gdf_incluidos_proj_pg2 = gdf_incluidos.to_crs("EPSG:3857")
        gdf_limítrofes_proj = gdf_limítrofes.to_crs("EPSG:3857")
        punto_central_proj = transform(pyproj.Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True).transform, punto_central)
        circle_proj_pg2 = transform(pyproj.Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True).transform, circle)

        with PdfPages(output_path) as pdf:
            fig1, (ax_mapa, ax_lista) = plt.subplots(1, 2, figsize=(11.69, 8.27), gridspec_kw={'width_ratios': [2, 1]})
            gdf_continental_proj.plot(ax=ax_mapa, edgecolor="black", facecolor="none", linewidth=0.5)
            gdf_incluidos_proj_pg1.plot(ax=ax_mapa, facecolor=color_deseado, edgecolor="black", linewidth=0.5)
            ax_mapa.plot(punto_central_proj.x, punto_central_proj.y, "ro", markersize=3)
            ax_mapa.set_aspect('equal')
            ax_mapa.axis("off")
            ax_mapa.set_title("Mapa general de Argentina", fontsize=10)
            ax_lista.axis("off")
            ax_lista.text(0.5, 0.95, "Departamentos incluidos", ha="center", va="top", fontsize=9, fontweight='bold')
            incluidos = gdf_incluidos["departamento"].sort_values().tolist()
            cols = 3
            max_per_col = int(len(incluidos) / cols) + 1
            for col in range(cols):
                x_pos = 0.05 + col * 0.3
                for i in range(max_per_col):
                    idx = col * max_per_col + i
                    if idx >= len(incluidos):
                        break
                    y = 0.90 - i * 0.03
                    nombre = incluidos[idx]
                    if len(nombre) > 25:
                        nombre = "\n".join([nombre[j:j+25] for j in range(0, len(nombre), 25)])
                    ax_lista.text(x_pos, y, f"• {nombre}", fontsize=6.5, ha="left", va="top")
            fig1.subplots_adjust(left=0.03, right=0.97, top=0.90, bottom=0.08)
            pdf.savefig(fig1)
            plt.close(fig1)

            fig2, ax_zoom = plt.subplots(figsize=(11.69, 8.27))
            gdf_limítrofes_proj.plot(ax=ax_zoom, facecolor="#DDDDDD", edgecolor="black", linewidth=0.4)
            gdf_incluidos_proj_pg2.plot(ax=ax_zoom, facecolor=color_deseado, edgecolor="black", linewidth=0.6)
            gpd.GeoSeries([circle_proj_pg2], crs="EPSG:3857").boundary.plot(ax=ax_zoom, color="blue", linewidth=1)
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
            pdf.savefig(fig2)
            plt.close(fig2)

        if not os.path.exists(output_path):
            raise FileNotFoundError(f"No se generó el PDF en {output_path}")

        link_pdf = subir_a_drive(output_path, nombre_final)
        return jsonify({"url": link_pdf}), 200

    except Exception as e:
        print("ERROR:", str(e))
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
