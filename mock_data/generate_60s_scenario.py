"""
Generador de Dataset Sintético para el Ensayo de 60 Segundos en Microred de BT (7 Nodos).
Genera el archivo mock_data/scenario_60s_bt.json con discretización dt = 0.5 s (120 pasos).
Eventos incorporados:
  - t = 0s a 15s : Operación nominal base (Solar 10 kW, Cargas base = 15 kW total).
  - t = 15s      : Reescalón de demanda (+2.0 kW en Nodo 4, +3.0 kW en Nodo 6).
  - t = 30s      : Rampa de sombreado solar (reducción rápida del 70% en Nodo 3).
  - t = 45s a 60s: Perturbaciones de comunicación P2P (loss 20%, latency 100-300 ms, corte enlace N2-N3 a t=50s).
"""

import json
import os
import random

def generate_scenario():
    dt = 0.5
    total_steps = 120  # 60 segundos
    scenario = []

    # Cargas base nominales (W, var)
    base_loads = {
        "4": {"P_w": 3000.0, "Q_var": 1200.0},
        "5": {"P_w": 4500.0, "Q_var": 1800.0},
        "6": {"P_w": 5000.0, "Q_var": 2000.0},
        "7": {"P_w": 2500.0, "Q_var": 1000.0},
    }

    random.seed(42)  # Reproducibilidad

    for step in range(1, total_steps + 1):
        t = (step - 1) * dt

        # 1. Perfil Solar (Nodo 3)
        if t < 30.0:
            poa = 1000.0  # 1000 W/m2 -> 10 kW nominal
            p_pv = 10000.0
        elif t < 35.0:
            # Rampa descendente de 30s a 35s
            frac = (35.0 - t) / 5.0
            poa = 300.0 + 700.0 * frac
            p_pv = 3000.0 + 7000.0 * frac
        else:
            poa = 500.0  # Estabilización en 5 kW
            p_pv = 5000.0

        solar_data = {
            "POA": round(poa, 2),
            "T_amb": 298.15,
            "P_available_w": round(p_pv, 2)
        }

        # 2. Perfil de Cargas
        current_loads = {}
        for n_id, load_vals in base_loads.items():
            p_w = load_vals["P_w"]
            q_var = load_vals["Q_var"]

            # Reescalón de demanda a los t >= 15s en N4 y N6
            if t >= 15.0:
                if n_id == "4":
                    p_w += 2000.0  # +2 kW
                    q_var += 800.0
                elif n_id == "6":
                    p_w += 3000.0  # +3 kW
                    q_var += 1200.0

            # Desconexión parcial de Carga 2 (Nodo 5) a los t >= 40s
            if t >= 40.0 and n_id == "5":
                p_w -= 2500.0  # -2.5 kW
                q_var -= 1000.0

            # Ruido estocástico ligero (+-2%)
            noise_p = random.uniform(-0.02, 0.02) * p_w
            noise_q = random.uniform(-0.02, 0.02) * q_var

            current_loads[n_id] = {
                "P_w": round(p_w + noise_p, 2),
                "Q_var": round(q_var + noise_q, 2)
            }

        # 3. Impairments de Comunicación P2P
        if t < 45.0:
            loss_rate = 0.0
            latency_ms = 10.0
            disconnected_links = []
        else:
            loss_rate = 0.20  # 20% pérdidas
            latency_ms = round(random.uniform(100.0, 300.0), 2)  # Latencia 100-300 ms
            disconnected_links = [["2", "3"]] if t >= 50.0 else []

        impairment_data = {
            "packet_loss_rate": loss_rate,
            "latency_ms": latency_ms,
            "disconnected_links": disconnected_links
        }

        step_record = {
            "step": step,
            "t_sec": round(t, 2),
            "solar_node_3": solar_data,
            "loads": current_loads,
            "comms_impairment": impairment_data
        }
        scenario.append(step_record)

    out_dir = os.path.dirname(os.path.abspath(__file__))
    out_file = os.path.join(out_dir, "scenario_60s_bt.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(scenario, f, indent=2)

    print(f"Dataset sintético de 60s generado exitosamente en: {out_file}")
    print(f"Total de pasos: {len(scenario)} (dt = {dt}s)")

if __name__ == "__main__":
    generate_scenario()
