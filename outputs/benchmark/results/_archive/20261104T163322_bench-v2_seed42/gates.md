# Resumen de Gates de Aceptación por Variante

| Variante | G1 (t_s) | G2 (Δf) | G3 (Q) | G4 (P) | G5 (V) | G6 (ω) | G7 (CFL) | G8 (τ) | Todos |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Droop Puro (Guerrero 2011) | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | PASS | N/A | FAIL |
| Droop Puro (Optimizado) | FAIL | FAIL | FAIL | FAIL | FAIL | FAIL | PASS | N/A | FAIL |
| PI Centralizado (Canónico) | PASS | PASS | FAIL | FAIL | PASS | PASS | PASS | N/A | FAIL |
| PI Centralizado (Optimizado) | PASS | PASS | FAIL | FAIL | PASS | PASS | PASS | N/A | FAIL |
| DAPI (Simpson-Porco 2015) | PASS | PASS | PASS | PASS | FAIL | PASS | PASS | PASS | FAIL |
| DAPI (Optimizado) | PASS | PASS | PASS | PASS | FAIL | PASS | PASS | PASS | FAIL |
| FTS Tiempo Finito (Wang 2021) | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **PASS** |
| FTS Tiempo Finito (Optimizado) | PASS | PASS | PASS | PASS | PASS | PASS | FAIL | FAIL | FAIL |
| FxTS Tiempo Fijo (La Tesis - Certificado) | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **PASS** |

---

## Detalle de Causa de Falla en Gates No Aprobados (Explicabilidad V-02 / S-21)

| Variante | Gate | Descripción | Valor Observado | Umbral Normativo | Causa / Razón Diagnosticada |
|---|:---:|---|:---:|:---:|---|
| Droop Puro (Guerrero 2011) | **G1** | t_s a banda normativa (|e_f| <= 0.10 Hz) <= cota Lyapunov T_f | `inf` | `52.5400` | No asienta en la banda normativa (|e_f| <= 0.100 Hz) |
| Droop Puro (Guerrero 2011) | **G2** | Amplitud ciclo limite en estado estacionario restaurado | `0.0000` | `0.2000` | Frecuencia no restaurada: error residual 0.4667 Hz > umbral 0.100 Hz (restored=False) |
| Droop Puro (Guerrero 2011) | **G3** | Desviacion max entre ratios Q_i / Q_max | `0.0800` | `0.0200` | Dispersión reactiva 0.0800 >= 0.020 |
| Droop Puro (Guerrero 2011) | **G4** | Desviacion max entre ratios P_i / P_max | `0.1867` | `0.0200` | Dispersión activa 0.1867 >= 0.020 |
| Droop Puro (Guerrero 2011) | **G5** | Banda objetivo secundario +-0.5% (Energies eq. 12) | `0.2000` | `0.0050` | Error estacionario tensión 0.2000 p.u. > umbral 0.005 p.u. |
| Droop Puro (Guerrero 2011) | **G6** | Banda objetivo secundario +-0.1 Hz (Energies eq. 11) | `0.4667` | `0.1000` | Error estacionario frecuencia 0.4667 Hz > umbral 0.100 Hz |
| Droop Puro (Optimizado) | **G1** | t_s a banda normativa (|e_f| <= 0.10 Hz) <= cota Lyapunov T_f | `inf` | `52.5400` | No asienta en la banda normativa (|e_f| <= 0.100 Hz) |
| Droop Puro (Optimizado) | **G2** | Amplitud ciclo limite en estado estacionario restaurado | `0.0000` | `0.2000` | Frecuencia no restaurada: error residual 0.4667 Hz > umbral 0.100 Hz (restored=False) |
| Droop Puro (Optimizado) | **G3** | Desviacion max entre ratios Q_i / Q_max | `0.0800` | `0.0200` | Dispersión reactiva 0.0800 >= 0.020 |
| Droop Puro (Optimizado) | **G4** | Desviacion max entre ratios P_i / P_max | `0.1867` | `0.0200` | Dispersión activa 0.1867 >= 0.020 |
| Droop Puro (Optimizado) | **G5** | Banda objetivo secundario +-0.5% (Energies eq. 12) | `0.2000` | `0.0050` | Error estacionario tensión 0.2000 p.u. > umbral 0.005 p.u. |
| Droop Puro (Optimizado) | **G6** | Banda objetivo secundario +-0.1 Hz (Energies eq. 11) | `0.4667` | `0.1000` | Error estacionario frecuencia 0.4667 Hz > umbral 0.100 Hz |
| PI Centralizado (Canónico) | **G3** | Desviacion max entre ratios Q_i / Q_max | `0.0800` | `0.0200` | Dispersión reactiva 0.0800 >= 0.020 |
| PI Centralizado (Canónico) | **G4** | Desviacion max entre ratios P_i / P_max | `0.1867` | `0.0200` | Dispersión activa 0.1867 >= 0.020 |
| PI Centralizado (Optimizado) | **G3** | Desviacion max entre ratios Q_i / Q_max | `0.0800` | `0.0200` | Dispersión reactiva 0.0800 >= 0.020 |
| PI Centralizado (Optimizado) | **G4** | Desviacion max entre ratios P_i / P_max | `0.1867` | `0.0200` | Dispersión activa 0.1867 >= 0.020 |
| DAPI (Simpson-Porco 2015) | **G5** | Banda objetivo secundario +-0.5% (Energies eq. 12) | `0.0088` | `0.0050` | Error estacionario tensión 0.0088 p.u. > umbral 0.005 p.u. |
| DAPI (Optimizado) | **G5** | Banda objetivo secundario +-0.5% (Energies eq. 12) | `0.0067` | `0.0050` | Error estacionario tensión 0.0067 p.u. > umbral 0.005 p.u. |
| FTS Tiempo Finito (Optimizado) | **G7** | Cota nodal soporte: dt * d_max * (c1 + c2) < 1.0 (gobernante espectral 16.2% en TEORIA.tex:218) | `1.5977` | `1.0000` | CFL espectral 1.5977 >= 1.0 |
| FTS Tiempo Finito (Optimizado) | **G8** | Cota analítica de retardo admisible: 2.0 / (lambda_max * g_ef) - dt | `-187.0000` | `50.0000` | tau_crit=-187.0 ms < umbral 50.0 ms |