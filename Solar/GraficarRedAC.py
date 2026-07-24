import matplotlib.pyplot as plt
import csv
import os
import numpy as np

def graficar_red_ac(archivo="resultados.csv"):
    if not os.path.exists(archivo):
        print(f"Error: No se encontró el archivo {archivo}")
        return

    # Inicializar listas para almacenar los datos
    tiempo = []
    Va = []
    Vb = []
    Vc = []
    Valpha = []
    Vbeta = []
    Vd = []   # Se asume que Vd_red se guarda en esta columna (representa Vd de Park)
    Vq = []   # Se asume que Vq_red se guarda en esta columna (representa Vq de Park)

    # Se espera que el CSV tenga el siguiente header:
    # ["Tiempo", "Wr", "Tm", "Wg", "Tg",
    #  "Vq", "Iq", "Vdc", "Pdc_in",
    #  "Vdt", "Idi", "Idiref", "Pdc_out",
    #  "Vd_red", "Vq_red", "Fsys_red", "Pw", "Pq", "Ws",
    #  "Va", "Vb", "Vc", "Valpha", "Vbeta"]
    with open(archivo, "r") as f:
        reader = csv.reader(f)
        header = next(reader)
        for row in reader:
            try:
                tiempo.append(float(row[0]))
                # Las señales trifásicas están en las columnas "Va", "Vb", "Vc" (índices 19, 20, 21)
                Va.append(float(row[19]))
                Vb.append(float(row[20]))
                Vc.append(float(row[21]))
                # La transformada de Clarke está en las columnas "Valpha", "Vbeta" (índices 22, 23)
                Valpha.append(float(row[22]))
                Vbeta.append(float(row[23]))
                # La transformada de Park se guarda en "Vd_red" y "Vq_red" (índices 13 y 14)
                Vd.append(float(row[13]))
                Vq.append(float(row[14]))
            except Exception as e:
                continue

    tiempo = np.array(tiempo)

    # Crear 3 subplots
    fig, axs = plt.subplots(3, 1, figsize=(10, 12), sharex=True)

    # Subplot 1: Señales trifásicas: Va, Vb, Vc
    axs[0].plot(tiempo, Va, label="Va", color="gold")
    axs[0].plot(tiempo, Vb, label="Vb", color="blue")
    axs[0].plot(tiempo, Vc, label="Vc", color="red")
    axs[0].set_title("Señales trifásicas")
    axs[0].set_ylabel("Voltaje (V)")
    axs[0].legend()
    axs[0].grid()

    # Subplot 2: Transformada de Clarke: Valpha y Vbeta
    axs[1].plot(tiempo, Valpha, label="Valpha", color="purple")
    axs[1].plot(tiempo, Vbeta, label="Vbeta", color="orange")
    axs[1].set_title("Transformada de Clarke")
    axs[1].set_ylabel("Voltaje (V)")
    axs[1].legend()
    axs[1].grid()

    # Subplot 3: Transformada de Park: Vd y Vq
    axs[2].plot(tiempo, Vd, label="Vd", color="blue")
    axs[2].plot(tiempo, Vq, label="Vq", color="magenta")
    axs[2].set_title("Transformada de Park")
    axs[2].set_ylabel("Voltaje (V)")
    axs[2].set_xlabel("Tiempo (s)")
    axs[2].legend()
    axs[2].grid()

    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    graficar_red_ac()
