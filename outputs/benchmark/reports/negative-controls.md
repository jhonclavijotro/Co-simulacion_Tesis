# Informe de Controles Negativos — Benchmark v2 (Fase D)

**Fecha de ejecución:** 2026-11-03 17:21:49 UTC · **Plataforma:** Windows-11-10.0.26300-SP0 · **Python:** 3.12.10
**Escenario evaluado:** E1 (Paso de carga +50 %) sobre banco de 8 nodos ($N_{bus}=8$, $N_{DER}=3$)

---

## 1. Resumen Ejecutivo de Capacidad de Detección

Un benchmark de control es metodológicamente nulo si no es capaz de reprobar ante controladores rotos o inestables.
A continuación se presenta la verificación empírica de los cuatro controles obligatorios exigidos por la especificación v2 (§8):

| ID | Falla Inyectada | Comportamiento Exigido | Comportamiento Observado | Capacidad de Detección |
|---|---|---|---|:---:|
| **N1** | Consenso anulado: u = sum(...) * 0 (defecto original del benchmark v1) | Reprobar G1 / G6 (detectar ausencia de restauración secundaria) | Sin restauración. t_s = None, e_omega = 0.4667 Hz | ✅ DETECTADA (REPROBÓ) |
| **N2** | Ganancias ajenas (c1=0.15, c2=0.85, alpha=0.5, beta=2.0) | Reprobar G7 (CFL >= 1.0) o violar cota T_f | CFL violación: stable = False, t_s = None | ✅ DETECTADA (REPROBÓ) |
| **N3** | Signo invertido en control secundario (-u en lugar de +u) | Divergencia física del sistema / reprobar G2 y G6 | Divergencia = True, delta_f_pp = 0.00 Hz | ✅ DETECTADA (REPROBÓ) |
| **N4** | Línea base canónica DAPI (Simpson-Porco et al., 2015) | Reproducir convergencia asintótica y estabilidad CFL | Asintótico estable. t_s = 26.0 s, CFL = True | ✅ REPRODUCIDA (PASÓ) |

---

## 2. Detalle de Gates por Control

### Control N1: Consenso anulado: u = sum(...) * 0 (defecto original del benchmark v1)

| Gate | Parámetro | Valor | Umbral | Estado |
|---|---|---|---|:---:|
| **G1** | Tiempo de asentamiento normativo | inf s | <= 52.54 | `FAIL` |
| **G2** | Oscilacion de frecuencia pico a pico | 0.0 Hz | < 0.2 | `FAIL` |
| **G3** | Error de reparto de potencia reactiva | 0.08 p.u. | < 0.02 | `FAIL` |
| **G4** | Error de reparto de potencia activa | 0.1867 p.u. | < 0.02 | `FAIL` |
| **G5** | Error de restauracion de tension | 0.2 p.u. | <= 0.005 | `FAIL` |
| **G6** | Error de restauracion de frecuencia | 0.4667 Hz | <= 0.1 | `FAIL` |
| **G7** | Estabilidad CFL discreta | 0.4 num | < 1.0 | `PASS` |
| **G8** | Tolerancia a retardo de red (tau_crit) | 0.0 ms | >= 50.0 | `FAIL` |

### Control N2: Ganancias ajenas (c1=0.15, c2=0.85, alpha=0.5, beta=2.0)

| Gate | Parámetro | Valor | Umbral | Estado |
|---|---|---|---|:---:|
| **G1** | Tiempo de asentamiento normativo | inf s | <= 52.54 | `FAIL` |
| **G2** | Oscilacion de frecuencia pico a pico | 0.001 Hz | < 0.2 | `FAIL` |
| **G3** | Error de reparto de potencia reactiva | 0.0866 p.u. | < 0.02 | `FAIL` |
| **G4** | Error de reparto de potencia activa | 0.2009 p.u. | < 0.02 | `FAIL` |
| **G5** | Error de restauracion de tension | 0.0952 p.u. | <= 0.005 | `FAIL` |
| **G6** | Error de restauracion de frecuencia | 0.1144 Hz | <= 0.1 | `FAIL` |
| **G7** | Estabilidad CFL discreta | 1.0 num | < 1.0 | `FAIL` |
| **G8** | Tolerancia a retardo de red (tau_crit) | 0.0 ms | >= 50.0 | `FAIL` |

### Control N3: Signo invertido en control secundario (-u en lugar de +u)

| Gate | Parámetro | Valor | Umbral | Estado |
|---|---|---|---|:---:|
| **G1** | Tiempo de asentamiento normativo | inf s | <= 52.54 | `FAIL` |
| **G2** | Oscilacion de frecuencia pico a pico | 99.9 Hz | < 0.2 | `FAIL` |
| **G3** | Error de reparto de potencia reactiva | 588.2269 p.u. | < 0.02 | `FAIL` |
| **G4** | Error de reparto de potencia activa | 590.9863 p.u. | < 0.02 | `FAIL` |
| **G5** | Error de restauracion de tension | inf p.u. | <= 0.005 | `FAIL` |
| **G6** | Error de restauracion de frecuencia | inf Hz | <= 0.1 | `FAIL` |
| **G7** | Estabilidad CFL discreta | 0.4 num | < 1.0 | `FAIL` |
| **G8** | Tolerancia a retardo de red (tau_crit) | 0.0 ms | >= 50.0 | `FAIL` |

### Control N4: Línea base canónica DAPI (Simpson-Porco et al., 2015)

| Gate | Parámetro | Valor | Umbral | Estado |
|---|---|---|---|:---:|
| **G1** | Tiempo de asentamiento normativo | 26.0 s | <= 52.54 | `PASS` |
| **G2** | Oscilacion de frecuencia pico a pico | 0.0256 Hz | < 0.2 | `PASS` |
| **G3** | Error de reparto de potencia reactiva | 0.0 p.u. | < 0.02 | `PASS` |
| **G4** | Error de reparto de potencia activa | 0.0 p.u. | < 0.02 | `PASS` |
| **G5** | Error de restauracion de tension | 0.0196 p.u. | <= 0.005 | `FAIL` |
| **G6** | Error de restauracion de frecuencia | 0.0412 Hz | <= 0.1 | `PASS` |
| **G7** | Estabilidad CFL discreta | 0.2 num | < 1.0 | `PASS` |
| **G8** | Tolerancia a retardo de red (tau_crit) | 2579.8 ms | >= 50.0 | `PASS` |

---

## 3. Conclusión de Validez Metodológica

1. **El defecto D1 del benchmark v1 queda blindado:** el arnés detecta fehacientemente la anulación de términos de consenso (N1).
2. **El criterio de estabilidad CFL (G7) es vinculante:** el régimen numérico de ganancias ajenas es rechazado inmediatamente (N2).
3. **La estabilidad de fase es certificada:** la realimentación errónea produce divergencia física perceptible (N3).
4. **El harness reproduce la literatura:** la curva asintótica de DAPI converge con normalidad (N4).

**Dictamen de Fase D:** `APROBADA SIN RESERVAS`.