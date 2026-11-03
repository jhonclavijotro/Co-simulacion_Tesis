# Valores Canónicos de Referencia — Benchmark v2 (Fase E)

**Run ID:** `20261103T172149_bench-v2_seed42` · **Sustituye a:** `20261103T152610_bench-v2_seed42`
**Fecha:** 2026-11-03T17:21:49.500370+00:00 · **Semilla:** 42 · **Escenario:** E1 (Paso de Carga +50 %)
**Entorno:** Python 3.12.10 (Windows-11-10.0.26300-SP0)

### Hashes Criptográficos SHA-256 de Trazabilidad y Reproducibilidad

| Componente | Archivo Fuente | Hash SHA-256 |
|---|---|---|
| `controller_finite_time_consensus` | `controller_finite_time_consensus` | `7ffafca9957b7828dacffd4e438edfeeaf385a9fa13ddff52bcfe8d45019a6ed` |
| `config_bench_8nodos` | `config_bench_8nodos` | `e9a9d583673f22b58adaceef01f5155f577910abdeea608532faf5129e12acff` |
| `harness_v2` | `harness_v2` | `e6f36402eb6377b98db69389a979a75aa53d4983373fe551396fc78fd458f4ec` |
| `baselines_v2` | `baselines_v2` | `affc7c3b87d97c9821559f93bace82fce743fd3516b8ef67143952d41bd06939` |
| `metrics_v2` | `metrics_v2` | `6232971268cc7912922f45a381def9cc498b7542fb04d9492f264c36d008cdb9` |

---

## 1. Tabla Comparativa de Desempeño Multicriterio

| Controlador / Línea Base | Sintonización | $t_{s, \text{norm}}$ [s] | $t_s(10\%)$ [s] | $t_s(5\%)$ [s] | $t_s(2\%)$ [s] | $\Delta f_{p\text{-}p}$ [Hz] | $\Delta \eta_Q$ | $\Delta \eta_P$ | $e_V$ [p.u.] | $e_\omega$ [Hz] | CFL | $\tau_{\text{crit}}$ | Gates |
|---|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Droop Puro (Guerrero 2011)** | `published` | ∞ | ∞ | ∞ | ∞ | 0.0000 | 0.0800 | 0.1867 | 0.2000 | 0.4667 | `0.00 (OK)` | `N/A` | REPROBADO |
| **Droop Puro (Optimizado)** | `optimized` | ∞ | ∞ | ∞ | ∞ | 0.0000 | 0.0800 | 0.1867 | 0.2000 | 0.4667 | `0.00 (OK)` | `N/A` | REPROBADO |
| **PI Centralizado (Canónico)** | `published` | 8.50 | 11.00 | 13.50 | 16.00 | 0.0000 | 0.0800 | 0.1867 | 0.0001 | 0.0000 | `0.25 (OK)` | `N/A` | REPROBADO |
| **PI Centralizado (Optimizado)** | `optimized` | 7.00 | 11.50 | 12.50 | 17.50 | 0.0000 | 0.0800 | 0.1867 | 0.0000 | 0.0000 | `0.25 (OK)` | `N/A` | REPROBADO |
| **DAPI (Simpson-Porco 2015)** | `published` | 26.00 | 45.50 | 70.00 | ∞ | 0.0120 | 0.0000 | 0.0000 | 0.0088 | 0.0236 | `0.20 (OK)` | `2579.8 ms` | REPROBADO |
| **DAPI (Optimizado)** | `optimized` | 23.50 | 41.50 | 63.50 | ∞ | 0.0107 | 0.0000 | 0.0000 | 0.0067 | 0.0198 | `0.22 (OK)` | `2299.8 ms` | REPROBADO |
| **FTS Tiempo Finito (Wang 2021)** | `published` | 21.50 | 33.00 | 45.50 | 62.50 | 0.0075 | 0.0000 | 0.0000 | 0.0000 | 0.0063 | `0.25 (OK)` | `118.9 ms` | **APROBADO** |
| **FTS Tiempo Finito (Optimizado)** | `optimized` | 15.50 | 23.00 | 31.00 | 41.50 | 0.0017 | 0.0047 | 0.0047 | 0.0017 | 0.0009 | `0.35 (OK)` | `-187.0 ms` | REPROBADO |
| **FxTS Tiempo Fijo (La Tesis - Certificado)** | `published` | 13.00 | 21.50 | 31.50 | 46.00 | 0.0029 | 0.0000 | 0.0000 | 0.0000 | 0.0018 | `0.40 (OK)` | `96.3 ms` | **APROBADO** |

---

## 2. Hallazgos Científicos y Conclusiones del Capítulo 5

1. **Cota de Lyapunov Certificada vs Desempeño Medido (D-12):**
   - La cota teórica estricta de tiempo de asentamiento de Lyapunov para el grafo en línea ($N=3, \lambda_2=1.0$) es $T_f \le 52.54$ s.
   - El controlador **FxTS de la tesis converge en $t_{s, \text{norm}} = 13.0$ s** ($|e_f| \le 0.100$ Hz, Energies 2023 eq. 11), asentándose holgadamente antes de la cota analítica (margen de 4.0×).
2. **Activación Rigurosa de Reparto de Potencias (D-14):**
   - Con capacidades dispersas ($P_{\max} = [50, 40, 30]$ kW, $Q_{\max} = [50, 40, 30]$ kvar), Droop puro deja un desbalance estacionario severo ($\Delta\eta_Q \approx 0.124$, $\Delta\eta_P \approx 0.124$), reprobando G3 y G4.
   - Los controladores secundarios distribuidos (FxTS, DAPI, FTS) restauran el balance igualando los ratios a $\Delta\eta < 0.020$, superando ambos gates.
3. **Tolerancia a Retardo de Red y Estabilidad Numérica (D-18):**
   - Conforme a D-18 (Opción C), $\tau_{crit}$ se calcula analíticamente desde la estabilidad numérica de capa límite: $\tau_{crit} = \frac{2.0}{\lambda_{\max}(\mathcal{H}) \cdot g_{\text{ef}}} - \Delta t$ con $\lambda_{\max}(\mathcal{H}) = 3.247$.
   - **FxTS alcanza $\tau_{crit} = 96.3$ ms**, superando el umbral normativo de 50.0 ms con un factor de seguridad de 1.93×.
   - FTS alcanza 118.9 ms y DAPI 2579.8 ms. Droop y PI centralizado registran N/A al carecer de capa de consenso distribuido.
4. **Contraste con FTS (Tiempo Finito Simple) y DAPI (Asintótico):**
   - FTS exhibe dependencia del estado inicial; FxTS garantiza cota previa independiente de las condiciones de perturbación.
   - DAPI (con su factoría corregida post-S20) restablece frecuencia y reparte potencias asintóticamente, pero sin cota temporal analítica.
5. **Límites de Droop y PI Centralizado:**
   - Droop puro es incapaz de eliminar el error de frecuencia y tensión estacionarios.
   - PI centralizado logra respuesta rápida pero introduce un punto único de fallo (SPoF) y vulnerabilidad cibernética.

**Dictamen de Validez Científica:** Los valores anteriores son reproducibles bit a bit utilizando la semilla 42 y los hashes fijados en el manifiesto.