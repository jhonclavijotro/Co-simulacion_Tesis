import matplotlib.pyplot as plt
import csv
import os

def graficar_red_trifasica(archivo="resultados.csv"):
    if not os.path.exists(archivo):
        print(f"⚠ Error: No se encontró el archivo {archivo}")
        return

    tiempo = []
    Vd_red = []
    Vq_red = []
    Fsys_red = []
    Pw = []
    Pq = []
    Ws = []

    with open(archivo, "r") as file:
        reader = csv.reader(file)
        header = next(reader)  # Leer el header
        # Se asume que las columnas se guardaron en el siguiente orden:
        # 0: Tiempo, 1: Wr, 2: Tm, 3: Wg, 4: Tg,
        # 5: Vq, 6: Iq, 7: Vdc, 8: Pdc_in,
        # 9: Vdt, 10: Idi, 11: Idiref, 12: Pdc_out,
        # 13: Vd_red, 14: Vq_red, 15: Fsys_red, 16: Pw
        for row in reader:
            try:
                tiempo.append(float(row[0]))
                Vd_red.append(float(row[13]))
                Vq_red.append(float(row[14]))
                Fsys_red.append(float(row[15]))
                Pw.append(float(row[16]))
                Pq.append(float(row[17]))
                Ws.append(float(row[18]))
            except (ValueError, IndexError):
                continue

    # Crear subplots para cada variable
    fig, axs = plt.subplots(6, 1, figsize=(10, 12), sharex=True)

    axs[0].plot(tiempo, Vd_red, color="blue", label="Vd")
    axs[0].set_ylabel("Vd (V)")
    axs[0].set_title("Componente D (Vd)")
    axs[0].legend()
    axs[0].grid(True)

    axs[1].plot(tiempo, Vq_red, color="red", label="Vq")
    axs[1].set_ylabel("Vq (V)")
    axs[1].set_title("Componente Q (Vq)")
    axs[1].legend()
    axs[1].grid(True)

    axs[2].plot(tiempo, Fsys_red, color="green", label="Fsys")
    axs[2].set_ylabel("Fsys (Hz)")
    axs[2].set_title("Frecuencia del Bus (Fsys)")
    axs[2].legend()
    axs[2].grid(True)

    axs[3].plot(tiempo, Pw, color="gold", label="Pw")
    axs[3].set_ylabel("Pw (W)")
    axs[3].set_title("Potencia Activa Inyectada (Pw)")
    axs[3].legend()
    axs[3].grid(True)

    axs[4].plot(tiempo, Pq, color="purple", label="Pq")
    axs[4].set_ylabel("Pq (Var)")
    axs[4].set_title("Potencia Reactiva Inyectada (Pa)")
    axs[4].legend()
    axs[4].grid(True)

    axs[5].plot(tiempo, Ws, color="blue", label="Ws")
    axs[5].set_ylabel("Ws (m/s)")
    axs[5].set_title("Velocidad del Viento (Ws)")
    axs[5].set_xlabel("Tiempo (s)")
    axs[5].legend()
    axs[5].grid(True)

    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    graficar_red_trifasica()
