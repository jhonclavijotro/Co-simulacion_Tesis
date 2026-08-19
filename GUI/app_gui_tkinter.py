import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import sys
import threading
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from GUI.gui_command_center import GUICommandCenter

class MicrogridGUIApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Centro de Mando MAS - Control Secundario de Microrred")
        self.root.geometry("1120x720")
        self.root.configure(bg="#1e1e2e")

        # Configurar Estilos Oscuros Modernos
        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.configure_styles()

        # Instancia del motor del Centro de Mando
        self.top_bt = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", "topologia_BT_4nodos.csv"))
        self.top_mt = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", "topologia_MT_Nnodos.csv"))
        self.top_mallada = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", "topologia_BT_mallada_4nodos.csv"))
        
        self.command_center = GUICommandCenter(topology_csv=self.top_bt, mode="ONLINE", solver_mode="FBS", mesh_type="RADIAL")
        self.is_running = False

        self.build_ui()

    def configure_styles(self):
        self.style.configure(".", background="#1e1e2e", foreground="#cdd6f4", font=("Segoe UI", 10))
        self.style.configure("TLabelframe", background="#1e1e2e", foreground="#89b4fa", borderwidth=1, relief="solid")
        self.style.configure("TLabelframe.Label", background="#1e1e2e", foreground="#89b4fa", font=("Segoe UI", 11, "bold"))
        self.style.configure("TButton", background="#313244", foreground="#cdd6f4", font=("Segoe UI", 10, "bold"), borderwidth=0)
        self.style.map("TButton", background=[("active", "#45475a")], foreground=[("active", "#89b4fa")])
        self.style.configure("Accent.TButton", background="#89b4fa", foreground="#11111b", font=("Segoe UI", 10, "bold"))
        self.style.map("Accent.TButton", background=[("active", "#b4befe")])
        self.style.configure("Treeview", background="#181825", foreground="#cdd6f4", fieldbackground="#181825", rowheight=25)
        self.style.configure("Treeview.Heading", background="#313244", foreground="#89b4fa", font=("Segoe UI", 10, "bold"))

    def build_ui(self):
        # Header / Título Principal
        header_frame = tk.Frame(self.root, bg="#11111b", height=60)
        header_frame.pack(fill="x", side="top")
        
        lbl_title = tk.Label(
            header_frame,
            text="⚡ CENTRO DE MANDO: SISTEMA MULTI-AGENTE (MAS) - MICRORRED DISTRIBUIDA",
            font=("Segoe UI", 14, "bold"),
            bg="#11111b",
            fg="#89b4fa"
        )
        lbl_title.pack(side="left", padx=20, pady=15)

        lbl_status = tk.Label(
            header_frame,
            text="🟢 ESTADO: LISTO",
            font=("Segoe UI", 10, "bold"),
            bg="#11111b",
            fg="#a6e3a1"
        )
        lbl_status.pack(side="right", padx=20)
        self.lbl_status = lbl_status

        # Contenedor Principal
        main_container = tk.Frame(self.root, bg="#1e1e2e")
        main_container.pack(fill="both", expand=True, padx=15, pady=15)

        # PANEL IZQUIERDO: CONTROLES & CONFIGURACIÓN
        left_panel = tk.Frame(main_container, bg="#1e1e2e", width=400)
        left_panel.pack(side="left", fill="y", padx=(0, 10))

        # Grupo 1: Selección de Topología
        gf_topo = ttk.LabelFrame(left_panel, text=" 📍 Topología de Red ")
        gf_topo.pack(fill="x", pady=(0, 10), ipady=5)

        self.topo_var = tk.StringVar(value="BT")
        rb_bt = tk.Radiobutton(gf_topo, text="Red BT Radial (400V, R/X > 1)", variable=self.topo_var, value="BT", bg="#1e1e2e", fg="#cdd6f4", selectcolor="#313244", activebackground="#1e1e2e", command=self.on_topo_change)
        rb_bt.pack(anchor="w", padx=10, pady=2)
        rb_mallada = tk.Radiobutton(gf_topo, text="Red BT Mallada / Anillada (400V)", variable=self.topo_var, value="BT_MALLADA", bg="#1e1e2e", fg="#cdd6f4", selectcolor="#313244", activebackground="#1e1e2e", command=self.on_topo_change)
        rb_mallada.pack(anchor="w", padx=10, pady=2)
        rb_mt = tk.Radiobutton(gf_topo, text="Red Media Tensión (MT - 20kV)", variable=self.topo_var, value="MT", bg="#1e1e2e", fg="#cdd6f4", selectcolor="#313244", activebackground="#1e1e2e", command=self.on_topo_change)
        rb_mt.pack(anchor="w", padx=10, pady=2)
        
        btn_upload = ttk.Button(gf_topo, text="📁 Cargar Archivo .CSV / .XLSX", command=self.upload_file)
        btn_upload.pack(fill="x", padx=10, pady=5)

        # Grupo 2: Modo Operativo y Solucionador
        gf_mode = ttk.LabelFrame(left_panel, text=" ⚙️ Modos de Operación y Solver ")
        gf_mode.pack(fill="x", pady=(0, 10), ipady=5)

        tk.Label(gf_mode, text="Modo de Operación:", bg="#1e1e2e", fg="#cdd6f4").pack(anchor="w", padx=10, pady=(5, 0))
        self.mode_var = tk.StringVar(value="ONLINE")
        cb_mode = ttk.Combobox(gf_mode, textvariable=self.mode_var, values=["ONLINE (Grid-Connected)", "OFFLINE (Modo Isla)"], state="readonly")
        cb_mode.pack(fill="x", padx=10, pady=2)
        cb_mode.bind("<<ComboboxSelected>>", lambda e: self.on_mode_change())

        tk.Label(gf_mode, text="Solucionador PC Central:", bg="#1e1e2e", fg="#cdd6f4").pack(anchor="w", padx=10, pady=(5, 0))
        self.solver_var = tk.StringVar(value="FBS")
        cb_solver = ttk.Combobox(gf_mode, textvariable=self.solver_var, values=["FBS (Forward-Backward Sweep)", "SENSITIVITY (Matrices de Sensibilidad)"], state="readonly")
        cb_solver.pack(fill="x", padx=10, pady=2)
        cb_solver.bind("<<ComboboxSelected>>", lambda e: self.on_solver_change())

        # Selección dinámica de Tipo de Malla para Modo B
        self.lbl_mesh = tk.Label(gf_mode, text="Tipo de Malla (Modo B Sensibilidad):", bg="#1e1e2e", fg="#89b4fa")
        self.lbl_mesh.pack(anchor="w", padx=10, pady=(5, 0))
        
        self.mesh_var = tk.StringVar(value="RADIAL")
        self.cb_mesh = ttk.Combobox(
            gf_mode,
            textvariable=self.mesh_var,
            values=["RADIAL (Camino Único Shared R/X)", "RING_ZBUS (Matriz Impedancia Anillada Zbus)", "FULL_JACOBIAN (Jacobiana Invertida J^-1)"],
            state="disabled"
        )
        self.cb_mesh.pack(fill="x", padx=10, pady=2)
        self.cb_mesh.bind("<<ComboboxSelected>>", lambda e: self.on_mesh_change())

        # Grupo 3: Acciones y Despliegue
        gf_actions = ttk.LabelFrame(left_panel, text=" 🚀 Orquestación y Despliegue ")
        gf_actions.pack(fill="x", pady=(0, 10), ipady=5)

        btn_deploy = ttk.Button(gf_actions, text="📦 Despliegue Docker (1-Clic)", style="Accent.TButton", command=self.deploy_docker)
        btn_deploy.pack(fill="x", padx=10, pady=6)

        btn_start = ttk.Button(gf_actions, text="▶ Iniciar Co-Simulación (500 ms)", command=self.start_simulation)
        btn_start.pack(fill="x", padx=10, pady=4)

        btn_stop = ttk.Button(gf_actions, text="⏹ Detener Simulación", command=self.stop_simulation)
        btn_stop.pack(fill="x", padx=10, pady=4)

        # PANEL DERECHO: TELEMETRÍA, TABLA Y LOGS
        right_panel = tk.Frame(main_container, bg="#1e1e2e")
        right_panel.pack(side="right", fill="both", expand=True)

        gf_table = ttk.LabelFrame(right_panel, text=" 📊 Monitoreo de Nodos en Tiempo Real (Discretización 500 ms) ")
        gf_table.pack(fill="both", expand=True, pady=(0, 10))

        columns = ("nodo", "fuente", "v_pu", "v_volts", "p_w", "q_var", "estado")
        self.tree = ttk.Treeview(gf_table, columns=columns, show="headings", height=6)
        
        self.tree.heading("nodo", text="Nodo")
        self.tree.heading("fuente", text="Fuente / Tipo")
        self.tree.heading("v_pu", text="Tensión (p.u.)")
        self.tree.heading("v_volts", text="Tensión (V)")
        self.tree.heading("p_w", text="Potencia Activa (W)")
        self.tree.heading("q_var", text="Potencia Reactiva (VAR)")
        self.tree.heading("estado", text="Estado Agente")

        self.tree.column("nodo", width=60, anchor="center")
        self.tree.column("fuente", width=120, anchor="center")
        self.tree.column("v_pu", width=100, anchor="center")
        self.tree.column("v_volts", width=100, anchor="center")
        self.tree.column("p_w", width=130, anchor="center")
        self.tree.column("q_var", width=140, anchor="center")
        self.tree.column("estado", width=120, anchor="center")

        self.tree.pack(fill="both", expand=True, padx=5, pady=5)
        self.init_tree_data()

        gf_log = ttk.LabelFrame(right_panel, text=" 📝 Consola de Telemetría (MQTT & InfluxDB Log) ")
        gf_log.pack(fill="both", expand=True)

        self.log_text = tk.Text(gf_log, bg="#181825", fg="#a6e3a1", font=("Consolas", 9), borderwidth=0)
        self.log_text.pack(fill="both", expand=True, padx=5, pady=5)
        self.log("Sistema cargado e inicializado. Listo para despliegue de contenedores y co-simulación.")

    def init_tree_data(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        initial_rows = [
            ("1", "DIESEL (Slack)", "1.0000", "400.00", "0.0", "0.0", "🟢 Activo / Líder"),
            ("2", "SOLAR", "1.0000", "400.00", "0.0", "0.0", "🟢 Activo / Seguidor"),
            ("3", "EOLICA", "1.0000", "400.00", "0.0", "0.0", "🟢 Activo / Seguidor"),
            ("4", "HIDRICA + DEMANDA", "1.0000", "400.00", "0.0", "0.0", "🟢 Activo / Seguidor")
        ]
        for r in initial_rows:
            self.tree.insert("", "end", values=r)

    def log(self, msg):
        t_str = time.strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{t_str}] {msg}\n")
        self.log_text.see("end")

    def on_topo_change(self):
        val = self.topo_var.get()
        if val == "BT":
            self.command_center.set_topology(self.top_bt)
            self.log("Topología seleccionada: Red de Baja Tensión Radial (BT - 400V).")
        elif val == "BT_MALLADA":
            self.command_center.set_topology(self.top_mallada)
            self.log("Topología seleccionada: Red de Baja Tensión Mallada / Anillada (BT - 400V).")
        else:
            self.command_center.set_topology(self.top_mt)
            self.log("Topología seleccionada: Red de Media Tensión (MT - 20kV).")

    def on_mode_change(self):
        mode = "ONLINE" if "ONLINE" in self.mode_var.get() else "OFFLINE"
        self.command_center.mode = mode
        self.log(f"Modo de operación cambiado a: {mode}")

    def on_solver_change(self):
        if "SENSITIVITY" in self.solver_var.get():
            self.cb_mesh.config(state="readonly")
            self.lbl_mesh.config(fg="#89b4fa")
            self.log("Solucionador cambiado a SENSITIVITY. Selector de Malla activado.")
        else:
            self.cb_mesh.config(state="disabled")
            self.lbl_mesh.config(fg="#585b70")
            self.log("Solucionador cambiado a FBS (Forward-Backward Sweep).")

    def on_mesh_change(self):
        val = self.mesh_var.get()
        if "RING_ZBUS" in val:
            mesh_code = "RING_ZBUS"
        elif "FULL_JACOBIAN" in val:
            mesh_code = "FULL_JACOBIAN"
        else:
            mesh_code = "RADIAL"

        self.command_center.mesh_type = mesh_code
        self.log(f"Configuración de Malla asignada para Modo B: {mesh_code}")

    def upload_file(self):
        filepath = filedialog.askopenfilename(filetypes=[("Archivos CSV/Excel", "*.csv *.xlsx")])
        if filepath:
            self.command_center.set_topology(filepath)
            self.log(f"Archivo de topología/perfil cargado: {os.path.basename(filepath)}")
            messagebox.showinfo("Carga de Archivo", f"Perfil/Topología cargada exitosamente:\n{os.path.basename(filepath)}")

    def deploy_docker(self):
        out_yaml = self.command_center.deploy_containers("docker-compose.gui.yml")
        self.log(f"🚀 Despliegue de 1-Clic ejecutado: Manifiesto {out_yaml} generado con contenedores aislados.")
        messagebox.showinfo("Despliegue Docker (1-Clic)", f"Manifiesto autogenerado exitosamente:\n{out_yaml}\n\nContenedores de física y agente configurados.")

    def start_simulation(self):
        if self.is_running:
            return
        self.is_running = True
        self.lbl_status.config(text="🟡 ESTADO: EJECUTANDO (500 ms)", fg="#f9e2af")
        solver = "SENSITIVITY" if "SENSITIVITY" in self.solver_var.get() else "FBS"
        self.command_center.solver_mode = solver
        
        if solver == "SENSITIVITY":
            val = self.mesh_var.get()
            if "RING_ZBUS" in val:
                self.command_center.mesh_type = "RING_ZBUS"
            elif "FULL_JACOBIAN" in val:
                self.command_center.mesh_type = "FULL_JACOBIAN"
            else:
                self.command_center.mesh_type = "RADIAL"

        self.log(f"▶ Simulación iniciada en modo {self.command_center.mode} usando {solver} [Malla={self.command_center.mesh_type}]...")

        threading.Thread(target=self.run_sim_loop, daemon=True).start()

    def run_sim_loop(self):
        step = 0
        while self.is_running and step < 10:
            step += 1
            history = self.command_center.run_simulation(max_steps=1, port_rep=5588, port_pub=5589)
            if history:
                volts = history[0]["voltages"]
                self.root.after(0, self.update_tree, volts)
            time.sleep(0.5)

        self.is_running = False
        self.root.after(0, lambda: self.lbl_status.config(text="🟢 ESTADO: LISTO", fg="#a6e3a1"))
        self.root.after(0, lambda: self.log("Simulación finalizada."))

    def update_tree(self, voltages):
        for item in self.tree.get_children():
            node_id = int(self.tree.item(item)["values"][0])
            if node_id in voltages:
                v_pu = voltages[node_id]["V_pu"]
                v_volts = voltages[node_id]["V_volts"]
                vals = list(self.tree.item(item)["values"])
                vals[2] = f"{v_pu:.4f}"
                vals[3] = f"{v_volts:.2f}"
                self.tree.item(item, values=vals)
        self.log(f"Telemetría actualizada (Paso 500 ms): Nodo 1: {voltages.get(1,{}).get('V_volts')}V | Nodo 2: {voltages.get(2,{}).get('V_volts')}V")

    def stop_simulation(self):
        self.is_running = False
        self.log("⏹ Deteniendo simulación...")

if __name__ == "__main__":
    root = tk.Tk()
    app = MicrogridGUIApp(root)
    root.mainloop()
