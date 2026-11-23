"""
Simulación de cajas del Banco de Colombia (3 cajas M/M/1 independientes).
Ejecutar:  python src/simulacion_banco.py
Genera tablas (CSV), un reporte (TXT) y una gráfica (PNG) en la carpeta resultados/.
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ---------------- Parámetros ----------------
T_DIA = 480   # minutos (8 horas)
N_REP = 10    # réplicas (mínimo exigido: 10)
SALIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "resultados")
os.makedirs(SALIDA, exist_ok=True)

# (acción, tipo): (media servicio, media llegada, probabilidad dentro de la acción)
TABLA = {
    ("Retiro", "Rápido"):    (1, 1, 0.23),
    ("Retiro", "Normal"):    (2, 2, 0.40),
    ("Retiro", "Lento"):     (3, 3, 0.17),
    ("Retiro", "Muy lento"): (4, 3, 0.20),
    ("Pago", "Rápido"):      (3, 1, 0.10),
    ("Pago", "Normal"):      (3, 2, 0.20),
    ("Pago", "Lento"):       (5, 3, 0.30),
    ("Pago", "Muy lento"):   (7, 4, 0.40),
}
P_ACCION = {"Retiro": 0.70, "Pago": 0.30}

TIPOS = list(TABLA.keys())
PROBS = np.array([P_ACCION[a] * TABLA[(a, t)][2] for a, t in TIPOS])
MU_SRV = np.array([TABLA[k][0] for k in TIPOS], dtype=float)
MU_ARR = np.array([TABLA[k][1] for k in TIPOS], dtype=float)

ESCENARIOS = {
    "A: 3 cajas mixtas":         ["Mixta", "Mixta", "Mixta"],
    "B: 1 retiro + 2 pagos":     ["Retiro", "Pago", "Pago"],
    "C: 2 retiros + 1 pago":     ["Retiro", "Retiro", "Pago"],
    "D: 4 cajas mixtas (nueva)": ["Mixta"] * 4,
}


# ---------------- Modelo ----------------
def generar_clientes(rng):
    """Clientes de un día: llegada, acción, tipo y tiempo de servicio."""
    t, filas = 0.0, []
    while True:
        k = rng.choice(len(TIPOS), p=PROBS)
        t += rng.exponential(MU_ARR[k])
        if t > T_DIA:
            break
        filas.append((t, TIPOS[k][0], TIPOS[k][1], rng.exponential(MU_SRV[k])))
    return pd.DataFrame(filas, columns=["llegada", "accion", "tipo", "servicio"])


def simular(clientes, config, rng):
    """Cada caja es una cola FIFO M/M/1; el cliente elige al azar una caja habilitada."""
    df = clientes.copy()
    df["caja"] = 0
    for i, c in df.iterrows():
        opciones = [j for j, s in enumerate(config) if s in ("Mixta", c.accion)]
        df.at[i, "caja"] = rng.choice(opciones)
    libre = [0.0] * len(config)
    inicio, fin = [], []
    for _, c in df.iterrows():
        j = int(c.caja)
        ini = max(c.llegada, libre[j])
        libre[j] = ini + c.servicio
        inicio.append(ini)
        fin.append(libre[j])
    df["espera"] = np.array(inicio) - df.llegada
    df["sistema"] = np.array(fin) - df.llegada
    return df


def resumen(df):
    return pd.Series({
        "espera prom (min)": df.espera.mean(),
        "tiempo en sistema (min)": df.sistema.mean(),
        "espera máx (min)": df.espera.max(),
        "% que espera >5 min": (df.espera > 5).mean() * 100,
    })


def main():
    # Réplicas (mismos clientes para todos los escenarios -> comparación justa)
    res = {e: [] for e in ESCENARIOS}
    for r in range(N_REP):
        clientes = generar_clientes(np.random.default_rng(100 + r))
        for nombre, cfg in ESCENARIOS.items():
            sim = simular(clientes, cfg, np.random.default_rng(r))
            sim["replica"] = r + 1
            res[nombre].append(sim)
    res = {e: pd.concat(v) for e, v in res.items()}
    A = res["A: 3 cajas mixtas"]

    # Punto 1: atención por cajero
    p1 = A.groupby("caja").agg(clientes=("servicio", "size"),
                               atencion_prom=("servicio", "mean"),
                               espera_prom=("espera", "mean"),
                               sistema_prom=("sistema", "mean")).round(2)
    p1.index = [f"Caja {i+1}" for i in p1.index]
    p1.to_csv(f"{SALIDA}/p1_atencion_por_cajero.csv")

    # Puntos 2 y 3: usuarios por tipo
    cont = A.groupby(["replica", "accion", "tipo"]).size().unstack(["accion", "tipo"]).fillna(0).astype(int)
    p2 = cont.mean().round(1).rename("promedio_usuarios_por_dia")
    p2.to_csv(f"{SALIDA}/p2_promedio_usuarios_por_tipo.csv")
    cont.to_csv(f"{SALIDA}/p3_usuarios_por_replica.csv")
    totales = cont.sum(axis=1)

    # Punto 4: comparación de escenarios
    p4 = pd.DataFrame({e: resumen(d) for e, d in res.items()}).T.round(2)
    p4.to_csv(f"{SALIDA}/p4_comparacion_escenarios.csv")
    espera_accion = pd.DataFrame({e: d.groupby("accion").espera.mean() for e, d in res.items()}).T.round(2)
    espera_accion.to_csv(f"{SALIDA}/p4_espera_por_accion.csv")

    # Punto 5: mejor configuración exclusiva
    excl = p4.loc[["B: 1 retiro + 2 pagos", "C: 2 retiros + 1 pago"]]
    mejor = excl["espera prom (min)"].idxmin()

    # Gráfica
    plt.figure(figsize=(8, 4.5))
    ax = p4["espera prom (min)"].plot(kind="bar", color=["#999", "#4C78A8", "#F58518", "#54A24B"], rot=15)
    ax.set_ylabel("Espera promedio (min)")
    ax.set_title("Espera promedio por configuración de cajas")
    plt.tight_layout()
    plt.savefig(f"{SALIDA}/grafica_espera_promedio.png", dpi=150)

    # Reporte de texto
    pd.set_option("display.width", 200)
    lineas = [
        "RESULTADOS DE LA SIMULACIÓN (10 réplicas x 480 min)",
        "=" * 55,
        "\nPUNTO 1 - Atención por cajero (3 cajas mixtas)\n" + p1.to_string(),
        f"Menor tiempo de atención: {p1.atencion_prom.idxmin()} ({p1.atencion_prom.min()} min)",
        f"Mayor tiempo de atención: {p1.atencion_prom.idxmax()} ({p1.atencion_prom.max()} min)",
        "\nPUNTO 2 - Promedio de usuarios por tipo (por día)\n" + p2.to_string(),
        "\nPUNTO 3 - Usuarios por tipo en cada réplica\n" + cont.to_string(),
        f"Réplica con menos usuarios: {int(totales.idxmin())} ({int(totales.min())} usuarios)",
        "\nPUNTO 4 - Comparación de escenarios\n" + p4.to_string(),
        "\nEspera promedio por acción (min)\n" + espera_accion.to_string(),
        f"\nPUNTO 5 - Mejor configuración exclusiva: {mejor}",
    ]
    texto = "\n".join(lineas)
    with open(f"{SALIDA}/resultados.txt", "w", encoding="utf-8") as f:
        f.write(texto)
    print(texto)


if __name__ == "__main__":
    main()
