import csv
import cmath
import os

class ForwardBackwardSweepSolver:
    """
    Solucionador de flujo de potencia para redes radiales/mesheadas utilizando
    el algoritmo Forward-Backward Sweep (FBS) desarrollado desde cero en Python.
    No requiere Pandapower u otras librerías externas.
    """
    def __init__(self, V_base=400.0, S_base=100000.0):
        self.V_base = V_base          # Tensión base nominal [V] (fase-fase o equivalente)
        self.S_base = S_base          # Potencia base [VA]
        self.branches = []            # Lista de ramas: {from_node, to_node, R, X, Z}
        self.nodes = []               # Lista de nodos únicos
        self.slack_node = 1           # Nodo slack (subestación / fuente principal)
        self.tolerance = 1e-6         # Tolerancia de convergencia en p.u.
        self.max_iter = 100           # Número máximo de iteraciones

    def load_topology(self, csv_path):
        """Carga la topología de la red desde un archivo CSV."""
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
                z = complex(r, x)

                self.branches.append({
                    "from": u,
                    "to": v,
                    "R": r,
                    "X": x,
                    "Z": z
                })
                nodes_set.add(u)
                nodes_set.add(v)

        self.nodes = sorted(list(nodes_set))
        return len(self.nodes), len(self.branches)

    def solve(self, P_injections, Q_injections, V_slack=1.0):
        """
        Ejecuta el flujo de potencia Forward-Backward Sweep.
        
        Parámetros:
            P_injections: Dict {node_id: P_watts} (positivo = inyección/generación, negativo = demanda)
            Q_injections: Dict {node_id: Q_vars} (positivo = inyección, negativo = demanda)
            V_slack: Tensión en el nodo slack [p.u.] (complejo o real)
            
        Retorna:
            V_dict: Dict {node_id: V_pu_complex}
            converged: Bool
            iterations: Int
        """
        if not self.nodes:
            raise ValueError("No se ha cargado ninguna topología de red.")

        # Inicialización de voltajes (Flat start: 1.0 < 0°)
        V = {n: complex(1.0, 0.0) for n in self.nodes}
        V[self.slack_node] = complex(V_slack, 0.0) if isinstance(V_slack, (int, float)) else V_slack

        # Estructura del árbol (de hojas a raíz para Backward, de raíz a hojas para Forward)
        # Asumiendo red radial ordenada por niveles
        ordered_branches_backward = list(reversed(self.branches))
        ordered_branches_forward = self.branches

        converged = False
        iterations = 0

        for it in range(self.max_iter):
            iterations = it + 1
            V_prev = V.copy()

            # 1. Corrientes Nodal Inyectadas (I_node = conj(S / V))
            I_node = {}
            for n in self.nodes:
                if n == self.slack_node:
                    continue
                P_w = P_injections.get(n, 0.0)
                Q_var = Q_injections.get(n, 0.0)
                # Convertir a p.u.
                P_pu = P_w / self.S_base
                Q_pu = Q_var / self.S_base
                S_pu = complex(P_pu, Q_pu)
                I_node[n] = (S_pu / V[n]).conjugate()

            # 2. Barrido hacia Atrás (Backward Sweep): Cálculo de corrientes por rama
            I_branch = {}
            for br in ordered_branches_backward:
                u, v = br["from"], br["to"]
                # Corriente acumulada hacia el nodo v más las ramas aguas abajo
                child_currents = sum(
                    I_branch.get((v, child["to"]), 0.0)
                    for child in self.branches if child["from"] == v
                )
                I_branch[(u, v)] = I_node.get(v, 0.0) + child_currents

            # 3. Barrido hacia Adelante (Forward Sweep): Actualización de voltajes
            for br in ordered_branches_forward:
                u, v = br["from"], br["to"]
                # Z en p.u. = Z_ohm / (V_base^2 / S_base)
                Z_base = (self.V_base ** 2) / self.S_base
                Z_pu = br["Z"] / Z_base
                V[v] = V[u] - I_branch[(u, v)] * Z_pu

            # 4. Verificación de Convergencia
            max_diff = max(abs(abs(V[n]) - abs(V_prev[n])) for n in self.nodes)
            if max_diff < self.tolerance:
                converged = True
                break

        return V, converged, iterations

if __name__ == "__main__":
    solver = ForwardBackwardSweepSolver(V_base=400.0, S_base=100000.0)
    top_file = os.path.join(os.path.dirname(__file__), "..", "config", "topologia_BT_4nodos.csv")
    n_nodes, n_br = solver.load_topology(top_file)
    print(f"Topología BT cargada: {n_nodes} nodos, {n_br} ramas.")
    
    # Inyecciones de prueba: Nodo 2 inyecta 10 kW, Nodo 4 demanda 15 kW
    P_test = {2: 10000.0, 4: -15000.0}
    Q_test = {2: 2000.0, 4: -3000.0}
    
    voltages, conv, iters = solver.solve(P_test, Q_test)
    print(f"Resultado FBS (Convergencia={conv}, Iteraciones={iters}):")
    for node, v_val in voltages.items():
        v_abs_volts = abs(v_val) * solver.V_base
        print(f"  Nodo {node}: |V| = {abs(v_val):.4f} p.u. ({v_abs_volts:.2f} V), Angulo = {cmath.phase(v_val)*180/cmath.pi:.2f}°")
