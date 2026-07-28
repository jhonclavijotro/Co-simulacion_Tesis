import matplotlib.pyplot as plt
import csv
import os

def graficar_resultados(archivo="resultados.csv"):
    if not os.path.exists(archivo):
        print(f"⚠ Error: No se encontró el archivo {archivo}")
        return

    tiempo = []
    Wr = []
    Tm = []
    Wg = []
    Tg = []
    Vq_gen = []
    Iq_gen = []
    Vdc = []
    Pdc_in = []
    Vdt = []
    Idi = []
    Idiref = []
    Pdc_out = []
    
    with open(archivo, "r") as file:
        reader = csv.reader(file)
        header = next(reader)  # Se asume que existe un header
        for row in reader:
            try:
                tiempo.append(float(row[0]))
                Wr.append(float(row[1]))
                Tm.append(float(row[2]))
                Wg.append(float(row[3]))
                Tg.append(float(row[4]))
                Vq_gen.append(float(row[5]))
                Iq_gen.append(float(row[6]))
                Vdc.append(float(row[7]))
                Pdc_in.append(float(row[8]))
                Vdt.append(float(row[9]))
                Idi.append(float(row[10]))
                Idiref.append(float(row[11]))
                Pdc_out.append(float(row[12]))
            except (ValueError, IndexError):
                continue

    fig, axs = plt.subplots(3, 4, figsize=(18, 12), sharex=True)
    
    # Fila 1
    axs[0, 0].plot(tiempo, Wr, color="blue", label="Wr")
    axs[0, 0].set_title("Wr")
    axs[0, 1].plot(tiempo, Tm, color="red", label="Tm")
    axs[0, 1].set_title("Tm")
    axs[0, 2].plot(tiempo, Wg, color="green", label="Wg")
    axs[0, 2].set_title("Wg")
    axs[0, 3].plot(tiempo, Tg, color="purple", label="Tg")
    axs[0, 3].set_title("Tg")
    
    # Fila 2
    axs[1, 0].plot(tiempo, Vq_gen, color="blue", label="Vq generador")
    axs[1, 0].set_title("Vq generador")
    axs[1, 1].plot(tiempo, Iq_gen, color="red", label="Iq generador")
    axs[1, 1].set_title("Iq generador")
    axs[1, 2].plot(tiempo, Vdc, color="green", label="Vdc")
    axs[1, 2].set_title("Vdc")
    axs[1, 3].plot(tiempo, Pdc_in, color="purple", label="Pdc in")
    axs[1, 3].set_title("Pdc in")
    
    # Fila 3
    axs[2, 0].plot(tiempo, Vdt, color="blue", label="Vdt")
    axs[2, 0].set_title("Vdt")
    axs[2, 1].plot(tiempo, Idi, color="red", label="Idi")
    axs[2, 1].set_title("Idi")
    axs[2, 2].plot(tiempo, Idiref, color="green", label="Idiref")
    axs[2, 2].set_title("Idiref")
    axs[2, 3].plot(tiempo, Pdc_out, color="purple", label="Pdc out")
    axs[2, 3].set_title("Pdc out")
    
    for ax in axs.flat:
        ax.set_xlabel("Tiempo [s]")
        ax.legend()
        ax.grid(True)
    
    plt.tight_layout()
    plt.show()

    # Gráfica adicional: comparación Pdc_in vs Pdc_out
    plt.figure(figsize=(10, 5))
    plt.plot(tiempo, Pdc_in, label="Pdc in", color="blue")
    plt.plot(tiempo, Pdc_out, label="Pdc out", color="orange")
    plt.xlabel("Tiempo [s]")
    plt.ylabel("Potencia [W]")
    plt.title("Comparación entre Pdc in y Pdc out")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    graficar_resultados()
