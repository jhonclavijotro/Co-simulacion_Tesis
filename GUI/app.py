"""GUI - Centro de Mando MAS.

Aplicacion Flask para monitoreo en tiempo real, carga de perfiles,
y despliegue de contenedores.

Ejecutar:
  python GUI/app.py
  -> http://localhost:5000
"""

import csv
import json
import os
import threading
import time

from flask import Flask, jsonify, render_template, request

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(__file__), "data")
app.config["SECRET_KEY"] = "mas-secret-key-2026"
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# Estado global compartido
estado = {
    "co-simulacion": {"activa": False, "paso": 0, "tiempo": 0.0},
    "agentes": {},
    "historico": [],
    "meteo": [],
}


@app.route("/")
def index():
    return render_template("index.html", estado=estado)


@app.route("/api/estado")
def api_estado():
    return jsonify(estado)


@app.route("/api/historico")
def api_historico():
    ultimos = int(request.args.get("n", 100))
    return jsonify(estado["historico"][-ultimos:])


@app.route("/api/upload", methods=["POST"])
def api_upload():
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "No se envio archivo"}), 400
    f = request.files["file"]
    if f.filename == "":
        return jsonify({"ok": False, "error": "Nombre vacio"}), 400
    tipo = request.form.get("tipo", "demanda")
    dest = os.path.join(app.config["UPLOAD_FOLDER"], f"{tipo}_{f.filename}")
    f.save(dest)

    filas = 0
    try:
        with open(dest, "r") as fh:
            reader = csv.DictReader(fh)
            filas = sum(1 for _ in reader)
    except Exception:
        pass

    return jsonify({
        "ok": True,
        "archivo": os.path.basename(dest),
        "filas": filas,
        "tipo": tipo,
    })


@app.route("/api/deploy", methods=["POST"])
def api_deploy():
    data = request.get_json() or {}
    N = int(data.get("N", 3))
    modo = data.get("modo", "local")

    # En un entorno real, esto ejecutaria deploy.py
    thread = threading.Thread(
        target=_deploy_contenedores, args=(N, modo), daemon=True
    )
    thread.start()
    return jsonify({
        "ok": True,
        "mensaje": f"Despliegue iniciado: N={N}, modo={modo}",
    })


def _deploy_contenedores(N, modo):
    """Simula despliegue de contenedores.
    
    En produccion reemplazar con:
      subprocess.run([...deploy.py args...])
    """
    estado["co-simulacion"]["activa"] = True
    estado["co-simulacion"]["paso"] = 0
    estado["co-simulacion"]["tiempo"] = 0.0

    for i in range(1, N + 1):
        SoC = [0.8, 0.5, 0.3][i - 1] if i <= 3 else 0.5
        estado["agentes"][str(i)] = {
            "SoC": SoC,
            "P_ref": 0,
            "conectado": True,
        }

    # Simular pasos de co-simulacion
    tiempo_total = 10.0
    paso_maestro = 0.1
    paso = 0
    demanda = 15000
    while paso * paso_maestro < tiempo_total:
        t = paso * paso_maestro
        SoCs = [
            estado["agentes"][str(i)]["SoC"]
            for i in range(1, N + 1)
        ]
        SoC_avg = sum(SoCs) / N

        for i in range(1, N + 1):
            ag = estado["agentes"][str(i)]
            desvio = ag["SoC"] - SoC_avg
            fraccion = 1.0 / N + 2.0 * desvio
            P_ref = demanda * fraccion
            P_ref = max(-20000, min(20000, P_ref))
            ag["P_ref"] = round(P_ref, 1)
            ag["SoC"] = max(0, min(1, ag["SoC"] - P_ref * 0.1 / 1e6))

        estado["historico"].append({
            "paso": paso,
            "tiempo": round(t, 3),
            "SoC_avg": round(SoC_avg, 6),
            "demanda": demanda,
        })
        paso += 1
        time.sleep(0.01)

    estado["co-simulacion"]["activa"] = False
    print("[Deploy] Simulacion finalizada")


@app.route("/api/perfiles")
def api_perfiles():
    carpeta = app.config["UPLOAD_FOLDER"]
    archivos = []
    for fname in os.listdir(carpeta):
        if fname.endswith((".csv", ".xlsx")):
            ruta = os.path.join(carpeta, fname)
            archivos.append({
                "nombre": fname,
                "tamano": os.path.getsize(ruta),
                "modificado": os.path.getmtime(ruta),
            })
    return jsonify(archivos)


def main():
    app.run(host="0.0.0.0", port=5000, debug=True)


if __name__ == "__main__":
    main()
