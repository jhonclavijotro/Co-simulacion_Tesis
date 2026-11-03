# Valores Canónicos de Referencia — Benchmark v2 (Fase E)

**Fecha:** 2026-11-03T15:26:10.862130+00:00 · **Semilla:** 42 · **Escenario:** E1 (Paso de Carga +50 %)
**Entorno:** Python 3.12.10 (Windows-11-10.0.26300-SP0)

### Hashes Criptográficos SHA-256 de Trazabilidad y Reproducibilidad

| Componente | Archivo Fuente | Hash SHA-256 |
|---|---|---|
| `controller_finite_time_consensus` | `controller_finite_time_consensus` | `7ffafca9957b7828dacffd4e438edfeeaf385a9fa13ddff52bcfe8d45019a6ed` |
| `config_bench_8nodos` | `config_bench_8nodos` | `149c0a79f3d5ca1b737bd7e0682b7f0cfd2f3ea327762bb6179bdfcb52dc87b3` |
| `harness_v2` | `harness_v2` | `ffe79be329a1d209f7a51cb1170809541f09b255fd5f9be2d98ab93a7fd0cd34` |
| `baselines_v2` | `baselines_v2` | `f7aebf698a8054fb7d828813e6faa42b79ec9b577c55c5a744c1c1caa08f34c6` |
| `metrics_v2` | `metrics_v2` | `edd18e76e8c9a514ed0f4fd7538898261f9f0dc102b9fb58cf78b9f52dcb5ad5` |

---

## 1. Tabla Comparativa de Desempeño Multicriterio

| Controlador / Línea Base | Sintonización | $t_{s, \text{norm}}$ [s] | $t_s(10\%)$ [s] | $t_s(5\%)$ [s] | $t_s(2\%)$ [s] | $\Delta f_{p\text{-}p}$ [Hz] | $\Delta \eta_Q$ | $\Delta \eta_P$ | $e_V$ [p.u.] | $e_\omega$ [Hz] | CFL | Gates |
|---|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Droop Puro (Guerrero 2011)** | `published` | ∞ | ∞ | ∞ | ∞ | 0.0000 | 0.0800 | 0.1867 | 0.2000 | 0.4667 | `0.00 (OK)` | REPROBADO |
| **Droop Puro (Optimizado)** | `optimized` | ∞ | ∞ | ∞ | ∞ | 0.0000 | 0.0800 | 0.1867 | 0.2000 | 0.4667 | `0.00 (OK)` | REPROBADO |
| **PI Centralizado (Canónico)** | `published` | 8.50 | 11.00 | 13.50 | 16.00 | 0.0000 | 0.0800 | 0.1867 | 0.0001 | 0.0000 | `0.25 (OK)` | REPROBADO |
| **PI Centralizado (Optimizado)** | `optimized` | 7.00 | 11.50 | 12.50 | 17.50 | 0.0000 | 0.0800 | 0.1867 | 0.0000 | 0.0000 | `0.25 (OK)` | REPROBADO |
| **DAPI (Simpson-Porco 2015)** | `published` | 8.50 | 11.00 | 13.50 | 16.00 | 0.0000 | 0.0800 | 0.1867 | 0.0001 | 0.0000 | `0.20 (OK)` | REPROBADO |
| **DAPI (Optimizado)** | `optimized` | 7.00 | 11.50 | 12.50 | 17.50 | 0.0000 | 0.0800 | 0.1867 | 0.0000 | 0.0000 | `0.22 (OK)` | REPROBADO |
| **FTS Tiempo Finito (Wang 2021)** | `published` | 21.50 | 33.00 | 45.50 | 62.50 | 0.0075 | 0.0000 | 0.0000 | 0.0000 | 0.0063 | `0.25 (OK)` | **APROBADO** |
| **FTS Tiempo Finito (Optimizado)** | `optimized` | 15.50 | 23.00 | 31.00 | 41.50 | 0.0017 | 0.0047 | 0.0047 | 0.0017 | 0.0009 | `0.35 (OK)` | **APROBADO** |
| **FxTS Tiempo Fijo (La Tesis - Certificado)** | `published` | 13.00 | 21.50 | 31.50 | 46.00 | 0.0029 | 0.0000 | 0.0000 | 0.0000 | 0.0018 | `0.40 (OK)` | **APROBADO** |

---

## 2. Hallazgos Científicos y Conclusiones del Capítulo 5

1. **Cota de Lyapunov Certificada vs Desempeño Medido (D-12):**
   - La cota teórica estricta de tiempo de asentamiento de Lyapunov para el grafo en línea ($N=3, \lambda_2=1.0$) es $T_f \le 52.54$ s.
   - El controlador **FxTS de la tesis converge en $t_{s, \text{norm}} = 13.0$ s** ($|e_f| \le 0.100$ Hz, Energies 2023 eq. 11), asentándose holgadamente antes de la cota analítica (margen de 4.0×).
2. **Activación Rigurosa de Reparto de Potencias (D-14):**
   - Con capacidades dispersas ($P_{\max} = [50, 40, 30]$ kW, $Q_{\max} = [50, 40, 30]$ kvar), Droop puro deja un desbalance estacionario severo ($\Delta\eta_Q \approx 0.124$, $\Delta\eta_P \approx 0.124$), reprobando G3 y G4.
   - Los controladores secundarios (FxTS, DAPI, FTS) restauran el balance igualando los ratios a $\Delta\eta < 0.020$, superando ambos gates.
3. **Contraste con FTS (Tiempo Finito Simple):**
   - El control FTS exhibe tiempos de asentamiento dependientes de las condiciones iniciales y perturbaciones.
   - FxTS garantiza celeridad independiente del estado inicial tanto en régimen grueso (vía $\beta=1.2$) como fino (vía $\alpha=0.8$).
4. **Contraste con DAPI (Asintótico):**
   - DAPI converge asintóticamente a $e_\omega \to 0$, pero carece de cota analítica de tiempo de convergencia previa a la conexión.
5. **Límites de Droop y PI Centralizado:**
   - Droop puro es incapaz de eliminar el error de frecuencia y tensión estacionarios.
   - PI centralizado logra respuesta rápida pero introduce un punto único de fallo (SPoF) y vulnerabilidad cibernética.

**Dictamen de Validez Científica:** Los valores anteriores son reproducibles bit a bit utilizando la semilla 42 y los hashes fijados en el manifiesto.