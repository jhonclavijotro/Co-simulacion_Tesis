import matplotlib.pyplot as plt
import csv
import os


def graficar_resultados(archivo="resultados_hidrico.csv"):
    if not os.path.exists(archivo):
        print(f"Error: No se encontró el archivo {archivo}")
        return

    tiempo, Wr, Vdc, Pdc_in = [], [], [], []
    Pdc_out, Pw, V_corr, Cp, Lambda, Pm = [], [], [], [], [], []
    Fsys = []

    with open(archivo, "r") as f:
        reader = csv.reader(f)
        next(reader)
        for row in reader:
            try:
                tiempo.append(float(row[0]))
                Wr.append(float(row[1]))
                Vdc.append(float(row[7]))
                Pdc_in.append(float(row[8]))
                Pdc_out.append(float(row[12]))
                Pw.append(float(row[16]))
                V_corr.append(float(row[18]))
                Fsys.append(float(row[15]))
                Lambda.append(float(row[24]))
                Cp.append(float(row[25]))
                Pm.append(float(row[26]))
            except (ValueError, IndexError):
                continue

    fig, axs = plt.subplots(3, 3, figsize=(15, 10), sharex=True)

    axs[0, 0].plot(tiempo, Wr, color="blue")
    axs[0, 0].set_title("Wr [rad/s]")
    axs[0, 0].grid(True)

    axs[0, 1].plot(tiempo, V_corr, color="cyan")
    axs[0, 1].set_title("Vc [m/s]")
    axs[0, 1].grid(True)

    axs[0, 2].plot(tiempo, Vdc, color="green")
    axs[0, 2].set_title("Vdc [V]")
    axs[0, 2].grid(True)

    axs[1, 0].plot(tiempo, Pm, color="purple")
    axs[1, 0].set_title("Pm [W]")
    axs[1, 0].grid(True)

    axs[1, 1].plot(tiempo, Pdc_in, color="blue", label="Pdc in")
    axs[1, 1].plot(tiempo, Pdc_out, color="orange", label="Pdc out")
    axs[1, 1].set_title("Bus DC [W]")
    axs[1, 1].legend()
    axs[1, 1].grid(True)

    axs[1, 2].plot(tiempo, Pw, color="red")
    axs[1, 2].set_title("Pw [W]")
    axs[1, 2].grid(True)

    axs[2, 0].plot(tiempo, Cp, color="brown")
    axs[2, 0].set_title("Cp")
    axs[2, 0].grid(True)

    axs[2, 1].plot(tiempo, Lambda, color="magenta")
    axs[2, 1].set_title("lambda")
    axs[2, 1].grid(True)

    axs[2, 2].plot(tiempo, Fsys, color="green")
    axs[2, 2].set_title("Fsys [Hz]")
    axs[2, 2].grid(True)

    for ax in axs.flat:
        ax.set_xlabel("Tiempo [s]")

    plt.tight_layout()
    plt.show()

    plt.figure(figsize=(10, 4))
    plt.plot(tiempo, V_corr, label="Vc [m/s]", color="cyan")
    plt.plot(tiempo, [p / max(Pw) * max(V_corr) for p in Pw],
             label="Pw (norm)", color="red", alpha=0.7)
    plt.xlabel("Tiempo [s]")
    plt.ylabel("Vc [m/s] / Pw norm")
    plt.title("Correlacion Vc vs Pw")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    graficar_resultados()
