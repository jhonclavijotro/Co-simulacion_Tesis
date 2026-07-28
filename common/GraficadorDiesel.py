import matplotlib.pyplot as plt
import csv
import os


def graficar_resultados(archivo="resultados_diesel.csv"):
    if not os.path.exists(archivo):
        print(f"Error: No se encontró el archivo {archivo}")
        return

    tiempo, pref, Wm, Tm = [], [], [], []
    Pm, Pgen, Idiesel, Vdc = [], [], [], []
    Pw, Fsys = [], []

    with open(archivo, "r") as f:
        reader = csv.reader(f)
        next(reader)
        for row in reader:
            try:
                tiempo.append(float(row[0]))
                pref.append(float(row[1]))
                Wm.append(float(row[2]))
                Tm.append(float(row[3]))
                Pm.append(float(row[4]))
                Pgen.append(float(row[5]))
                Idiesel.append(float(row[6]))
                Vdc.append(float(row[7]))
                Pw.append(float(row[8]))
                Fsys.append(float(row[10]))
            except (ValueError, IndexError):
                continue

    fig, axs = plt.subplots(3, 3, figsize=(15, 10), sharex=True)

    axs[0, 0].plot(tiempo, Wm, color="blue", label="Wm")
    axs[0, 0].plot(tiempo, pref, color="red", alpha=0.5, label="pref")
    axs[0, 0].set_title("Wm vs pref [rad/s]")
    axs[0, 0].legend()
    axs[0, 0].grid(True)

    axs[0, 1].plot(tiempo, Tm, color="purple")
    axs[0, 1].set_title("Tm [Nm]")
    axs[0, 1].grid(True)

    axs[0, 2].plot(tiempo, Vdc, color="green")
    axs[0, 2].set_title("Vdc [V]")
    axs[0, 2].grid(True)

    axs[1, 0].plot(tiempo, Pm, color="brown", label="Pm")
    axs[1, 0].plot(tiempo, Pgen, color="orange", alpha=0.7, label="Pgen")
    axs[1, 0].set_title("Potencias [W]")
    axs[1, 0].legend()
    axs[1, 0].grid(True)

    axs[1, 1].plot(tiempo, Pw, color="red")
    axs[1, 1].set_title("Pw [W]")
    axs[1, 1].grid(True)

    axs[1, 2].plot(tiempo, Idiesel, color="cyan")
    axs[1, 2].set_title("Idiesel [A]")
    axs[1, 2].grid(True)

    axs[2, 0].plot(tiempo, Fsys, color="green")
    axs[2, 0].set_title("Fsys [Hz]")
    axs[2, 0].grid(True)

    axs[2, 1].axis("off")
    axs[2, 2].axis("off")

    for ax in axs.flat:
        ax.set_xlabel("Tiempo [s]")

    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    graficar_resultados()
