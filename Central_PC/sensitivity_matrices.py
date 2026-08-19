import csv
import os
import numpy as np

class SensitivityMatrixSolver:
    """
    Solucionador por Matrices de Sensibilidad Tensión-Potencia (dV/dQ y dV/dP).
    Soporta tres configuraciones de malla:
      - RADIAL: Suma de impedancias en camino único R/X compartido.
      - RING_ZBUS: Matriz de Impedancia Nodal Z_bus = inv(Y_bus) para redes anilladas/mesheadas.
      - FULL_JACOBIAN: Linearización con matriz Jacobiana invertida (J^-1).
    """
    def __init__(self, V_base=400.0, S_base=100000.0, mesh_type="RADIAL"):
        self.V_base = V_base
        self.S_base = S_base
        self.mesh_type = mesh_type.upper()
        self.nodes = []
        self.slack_node = 1
        self.S_VQ = {}  # Dict {(i, j): sensitivity_val}
        self.S_VP = {}  # Dict {(i, j): sensitivity_val}
        self.branches = []

    def set_mesh_type(self, mesh_type):
        """Permite cambiar dinámicamente la configuración de la malla."""
        self.mesh_type = mesh_type.upper()
        if self.branches:
            self._compute_matrices()

    def load_topology(self, csv_path, mesh_type=None):
        """Carga topología CSV y calcula las matrices de sensibilidad según el tipo de malla."""
        if mesh_type:
            self.mesh_type = mesh_type.upper()

        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"Archivo de topología no encontrado: {csv_path}")

        self.branches = []
        nodes_set = set()

        with open(csv_path, mode="r", encoding="utf-8") as f:
            valid_lines = [line for line in f if not line.strip().startswith("#")]
            reader = csv.DictReader(valid_lines)
            for row in reader:
                u = int(row["from_node"].strip())
                v = int(row["to_node"].strip())
                r = float(row["R_ohm"].strip())
                x = float(row["X_ohm"].strip())
                self.branches.append({"from": u, "to": v, "R": r, "X": x, "Z": complex(r, x)})
                nodes_set.add(u)
                nodes_set.add(v)

        self.nodes = sorted(list(nodes_set))
        self._compute_matrices()
        return len(self.nodes)

    def _compute_matrices(self):
        non_slack_nodes = [n for n in self.nodes if n != self.slack_node]
        Z_base = (self.V_base ** 2) / self.S_base
        self.S_VP = {}
        self.S_VQ = {}

        if self.mesh_type == "RADIAL":
            # Matriz de camino común para redes radiales (resistencia R y reactancia X compartida)
            for i in non_slack_nodes:
                for j in non_slack_nodes:
                    r_shared = sum(br["R"] for br in self.branches if br["to"] <= min(i, j)) / Z_base
                    x_shared = sum(br["X"] for br in self.branches if br["to"] <= min(i, j)) / Z_base
                    self.S_VP[(i, j)] = r_shared
                    self.S_VQ[(i, j)] = x_shared

        elif self.mesh_type in ["RING_ZBUS", "FULL_JACOBIAN"]:
            # Construcción de Y_bus en p.u. para redes malladas / anilladas
            n_map = {node_id: idx for idx, node_id in enumerate(self.nodes)}
            N = len(self.nodes)
            Y_bus = np.zeros((N, N), dtype=complex)

            for br in self.branches:
                u_idx = n_map[br["from"]]
                v_idx = n_map[br["to"]]
                z_pu = br["Z"] / Z_base
                y_pu = 1.0 / z_pu
                
                Y_bus[u_idx, u_idx] += y_pu
                Y_bus[v_idx, v_idx] += y_pu
                Y_bus[u_idx, v_idx] -= y_pu
                Y_bus[v_idx, u_idx] -= y_pu

            # Inversión restringida a la submatriz sin nodo slack
            slack_idx = n_map[self.slack_node]
            non_slack_indices = [i for i in range(N) if i != slack_idx]

            Y_reduced = Y_bus[np.ix_(non_slack_indices, non_slack_indices)]
            Z_reduced = np.linalg.inv(Y_reduced)

            for idx_i, node_i in enumerate(non_slack_nodes):
                for idx_j, node_j in enumerate(non_slack_nodes):
                    z_val = Z_reduced[idx_i, idx_j]
                    self.S_VP[(node_i, node_j)] = float(z_val.real)
                    self.S_VQ[(node_i, node_j)] = float(z_val.imag)

    def solve(self, P_injections, Q_injections, V_operating=None):
        """
        Calcula voltajes aproximados usando matrices de sensibilidad:
        V_i = V_base_i + sum_j ( S_VP[i,j]*dP_j + S_VQ[i,j]*dQ_j )
        """
        non_slack_nodes = [n for n in self.nodes if n != self.slack_node]
        V_res = {self.slack_node: complex(1.0, 0.0)}

        for i in non_slack_nodes:
            delta_V = 0.0
            for j in non_slack_nodes:
                P_pu = P_injections.get(j, 0.0) / self.S_base
                Q_pu = Q_injections.get(j, 0.0) / self.S_base

                s_vp = self.S_VP.get((i, j), 0.0)
                s_vq = self.S_VQ.get((i, j), 0.0)

                delta_V += (s_vp * P_pu + s_vq * Q_pu)

            v_mag = 1.0 + delta_V
            V_res[i] = complex(v_mag, 0.0)

        return V_res, True, 1

if __name__ == "__main__":
    solver = SensitivityMatrixSolver(V_base=400.0, S_base=100000.0, mesh_type="RING_ZBUS")
    top_file = os.path.join(os.path.dirname(__file__), "..", "config", "topologia_BT_4nodos.csv")
    solver.load_topology(top_file)

    P_test = {2: 10000.0, 4: -15000.0}
    Q_test = {2: 2000.0, 4: -3000.0}

    voltages, conv, iters = solver.solve(P_test, Q_test)
    print("Resultado Matrices de Sensibilidad en Malla RING_ZBUS:")
    for node, v_val in voltages.items():
        v_abs_volts = abs(v_val) * solver.V_base
        print(f"  Nodo {node}: |V| = {abs(v_val):.4f} p.u. ({v_abs_volts:.2f} V)")
