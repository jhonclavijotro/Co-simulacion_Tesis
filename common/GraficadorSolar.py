import matplotlib.pyplot as plt
import csv
import os

def graficar_resultados(archivo="resultados_solar.csv"):
    if not os.path.exists(archivo):
        print(f"Error: No se encontró el archivo {archivo}")
        return
    
    # Inicializar listas para almacenar datos
    tiempo, V_pv, I_pv, V_array, P_array = [], [], [], [], []
    V_ref, duty_cycle, I_dc, V_dc = [], [], [], []
    Pw, Pq, Idi, Iqi = [], [], [], []
    Vdi, Vqi, Fsys = [], [], []
    
    with open(archivo, "r") as file:
        reader = csv.reader(file)
        header = next(reader)
        for row in reader:
            try:
                tiempo.append(float(row[0]))
                V_pv.append(float(row[1]))
                I_pv.append(float(row[2]))
                V_array.append(float(row[3]))
                P_array.append(float(row[4]))
                V_ref.append(float(row[5]))
                duty_cycle.append(float(row[6]))
                I_dc.append(float(row[7]))
                V_dc.append(float(row[8]))
                Pw.append(float(row[9]))
                Pq.append(float(row[10]))
                Idi.append(float(row[11]))
                Iqi.append(float(row[12]))
                Vdi.append(float(row[13]))
                Vqi.append(float(row[14]))
                Fsys.append(float(row[15]))
            except (ValueError, IndexError):
                continue
    
    # Crear gráficos
    fig, axs = plt.subplots(3, 1, figsize=(10, 12), sharex=True)
    
    # Gráfico 1: Panel solar
    axs[0].plot(tiempo, V_array, label="Tensión del arreglo [V]", color="blue")
    axs[0].plot(tiempo, I_pv, label="Corriente del panel [A]", color="red")
    axs[0].plot(tiempo, P_array, label="Potencia [W]", color="green")
    axs[0].set_title("Comportamiento del Panel Solar")
    axs[0].legend()
    axs[0].grid(True)
    
    # Gráfico 2: Convertidor DC-DC
    axs[1].plot(tiempo, V_ref, label="Referencia MPPT [V]", color="purple")
    axs[1].plot(tiempo, duty_cycle, label="Ciclo de trabajo", color="orange")
    axs[1].plot(tiempo, V_dc, label="Tensión DC bus [V]", color="blue")
    axs[1].set_title("Control MPPT y Convertidor Boost")
    axs[1].legend()
    axs[1].grid(True)
    
    # Gráfico 3: Inversor y red
    axs[2].plot(tiempo, Pw, label="Potencia activa [W]", color="blue")
    axs[2].plot(tiempo, Pq, label="Potencia reactiva [VAR]", color="red")
    axs[2].plot(tiempo, Fsys, label="Frecuencia [Hz]", color="green")
    axs[2].set_title("Inversor Conectado a Red")
    axs[2].set_xlabel("Tiempo [s]")
    axs[2].legend()
    axs[2].grid(True)
    
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    graficar_resultados()