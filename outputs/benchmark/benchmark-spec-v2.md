# Especificación del benchmark v2 — Control secundario distribuido FxTS

**Versión:** 2.0 · **Fecha:** 2026-11-02 · **Autor:** HERMES (coordinación) · **Estado:** aprobada por el investigador
**Sustituye a:** `benchmark-spec.md` v1 (298 líneas), que queda obsoleto por los defectos D1–D8 de la solicitud **S-16** del registro `SIMULACION.md`.

---

## 1. Propósito

Evaluar el controlador de consenso en tiempo fijo (FxTS) de la tesis con referencias **objetivas y verificables**, de modo que las cifras del Capítulo 5 sean defendibles ante un jurado y reproducibles por un tercero.

**Criterio de éxito del benchmark mismo:** debe ser capaz de **reprobar**. Un harness en el que todos los escenarios pasan por construcción no mide nada.

**Por qué se reescribe desde cero.** El v1 no evalúa el controlador de la tesis:

| # | Defecto del v1 | Evidencia |
|---|---|---|
| D1 | Anula el término de consenso: `u = np.sum(V[:, k-1], axis=0, keepdims=True) * 0.0` | `baseline.py:140` |
| D2 | Ganancias ajenas: `c1=0.15, c2=0.85, p1=0.5, p2=2.0` | `baseline.py:69-79` |
| D3 | `T_max: float = 5.0` es constante, no derivada de `λ₂` | `metrics.py:124` |
| D4 | Viola su propio criterio CFL: `0.5·2·(0.15+0.85) = 2.5 > 1` | cálculo |
| D5 | El gate de 5 s rechazaría al controlador real (`t_s ≈ 10 s`) | contraste |
| D6 | `verification-report.md` en `FAIL` con la tabla de hallazgos vacía | archivo |
| D7 | Default inseguro: `finite_time_consensus.py:89-90` usa `c1=1.0, c2=1.0`; su propio `verify_discrete_cfl_stability(0.5, 2)` devuelve `(False, 2.0, 0.25)` | ejecutado |
| D8 | `n_nodes: 6`, `d_max: 5` describen una línea de 6 nodos, no el banco evaluado (3 agentes, diámetro 2) | contraste |

---

## 2. Alcance

**Decisión del investigador (2026-11-02): el benchmark cubre exclusivamente el banco de 8 nodos.**

| Parámetro | Valor |
|---|---|
| Barras eléctricas | $N_{\text{bus}} = 8$ — red radial BT, 400 V, 7 ramas |
| Agentes de consenso | $N_{\text{DER}} = 3$ — diésel (N1), solar (N2), BESS (N3) |
| Grafo de consenso | línea 1–2–3; $\lambda_2 = 1.0$; diámetro $d = 2$ |
| Potencia base | $S_{\text{base}} = 10$ kVA |
| Paso de integración | $\Delta t = 0.5$ s (2.0 Hz) |
| Escenario de referencia | `ESC-HIL-003_consolidado_rev5` (activo) |
| Cota analítica | $T_f \le 52.54$ s |

**Fuera de alcance:** anillo $C_5$, banco de 21 nodos ($\lambda_2 = 1.381966$, $T_f \le 37.81$ s), topología RED-GRANDE-21N. Esos datos pertenecen al canal de OpenCode y no se mezclan con la evaluación del controlador.

**Red CIGRE LV — trabajo futuro, no alcance.** Se evaluó y se descartó para esta tesis: la variante multi-alimentador tiene **40 barras** (18 residencial + 2 industrial + 20 comercial, 400 V) y **exige un bus fuente de 20 kV** con 3 transformadores 20/0.4 kV. Adoptarla no es ampliar el modelo actual, es construir un segundo modelo eléctrico completo. Queda registrada como línea de trabajo futuro del Capítulo 6, con dos referencias verificadas: `10.3390/eng7040147` (conteo de 40 barras) y `10.1109/TSG.2021.3067317` (Hu et al., control secundario de frecuencia sobre CIGRE LV).

---

## 3. Arquitectura en dos niveles

| Nivel | Qué ejecuta | Requisitos | Uso |
|---|---|---|---|
| **T1 · Software** | El controlador real, **importado** de `Agents/finite_time_consensus.py` | Python puro, determinista | Desarrollo, regresión, comparación de variantes, CI |
| **T2 · HIL** | El clúster físico de 6 Raspberry Pi 5 | Acceso al banco (universidad) | Validación final del Capítulo 5 |

**Regla no negociable:** el harness **importa** el controlador, no lo reimplementa. Un benchmark que duplica la lógica bajo prueba certifica su propia copia, no el artefacto.

**Viabilidad verificada:** `finite_time_consensus.py` solo importa `math`, `numpy` y `typing` — sin dependencias del proyecto. Un bucle de consenso de 3 agentes converge a `t_s = 11.0 s` frente a la cota de 52.54 s, con coste de **6.6 ms por corrida de 300 s**.

---

## 4. Artefacto bajo prueba

Configuración fijada. **Estos valores no se optimizan** — provienen de la cota de Lyapunov y optimizarlos invalidaría el certificado.

```python
FixedTimeConsensusAgent(
    alpha=0.8, beta=1.2, c1=0.25, c2=0.15,
    epsilon=1e-3, max_delta_V=0.10, max_delta_omega=1.0,
    max_stale_steps=4, f_ref=60.0
)
```

| Parámetro | Valor | Origen |
|---|---|---|
| $\alpha$ | 0.8 | `TEORIA.tex` §5.3 |
| $\beta$ | 1.2 | `TEORIA.tex` §5.3 |
| $c_1$ | 0.25 | `IMPLEMENTACION.tex` |
| $c_2$ | 0.15 | `IMPLEMENTACION.tex` |
| $\varepsilon$ | $10^{-3}$ | `sig_pow()` |
| $\lambda_2$ | 1.0 | grafo línea 3 agentes |
| $T_f$ | 52.54 s | `calculate_lyapunov_settling_time(1.0)` |

**Tarea previa obligatoria:** corregir el default de `finite_time_consensus.py:89-90` (D7). Una instanciación sin argumentos produce hoy un controlador inestable a $\Delta t = 0.5$.

---

## 5. Líneas base y protocolo de sintonización

**Decisión del investigador:** se ejecutan **las dos versiones** de cada línea base y se reportan ambas.

| Línea base | Qué demuestra | Parámetros (nº) | Referencia |
|---|---|---|---|
| Droop puro | Cota inferior; deja error de estado estacionario | $m_p$, $n_q$ (2) | `10.1109/TIE.2010.2066534` |
| PI centralizado | Techo de desempeño con infraestructura ideal; el SPoF a superar | $k_p$, $k_i$ (2) | `10.1109/TIE.2010.2066534` |
| Consenso asintótico (DAPI) | Referencia distribuida canónica, sin cota temporal | ganancia, $\varepsilon$ (1–2) | `10.1109/TIE.2015.2436879` |
| FTS (tiempo finito simple) | Contraste frente a FxTS; cota dependiente de $x(0)$ | $c_1$, $\alpha$ (2) | `10.3390/en14196266` |
| **FxTS (la tesis)** | **El aporte — sin sintonizar** | fijos (§4) | — |

**Protocolo:**

1. **Versión publicada:** parámetros tal como aparecen en el paper de origen.
2. **Versión optimizada:** algoritmo genético, población 50 × 30 generaciones, espacio log-uniforme $[10^{-3}, 10^{3}]$, **descartando toda combinación que no pase el CFL**.
3. **Función objetivo única e idéntica para todas:** $J = \int_0^{T} |e(t)|\,dt$ (IAE), sujeto a estabilidad.
4. **Mismos escenarios, mismas semillas y mismas condiciones iniciales** para todas las líneas base.

**Justificación:** Eberlein & Rudion 2021 (`10.1049/stg2.12036`) documentan que no existe un sistema de benchmark acordado para estabilidad de microrredes, y que la comparación solo es justa si **cada controlador se optimiza sobre el mismo objetivo antes de compararlo**.

**Asimetría declarada:** a las líneas base se les da el mejor ajuste posible; el FxTS corre con sus valores teóricos. La ventaja se otorga a los rivales, no al aporte.

**Costo medido:** 6.6 ms por corrida → 1.500 evaluaciones = 9.9 s por línea base → **49.4 s el barrido completo**.

---

## 6. Escenarios

Cada escenario se reporta **por separado**. Agregar oculta qué mecanismo falla.

| ID | Escenario | Configuración | Repeticiones |
|---|---|---|---|
| **E0** | Nominal | Sin perturbación; condiciones iniciales dispersas | 1 (determinista) |
| **E1** | Paso de carga | Escalones de ±50 % y ±100 % | 1 (determinista) |
| **E2** | Rampa de renovables | Perfil de irradiancia de `ESC-HIL-003` | 1 (determinista) |
| **E3** | Retardo de comunicación | Barrido 0, 10, 25, 50, 75, 100, 120 ms | 1 por punto |
| **E4** | Pérdida de paquetes | Bernoulli $p$ = 0.05 / 0.10 / 0.20; ráfagas 200 ms | **100 semillas → p50/p95/p99** |
| **E5** | Desconexión de enlace | *Plug-out* / *plug-in* de un DER | 1 (determinista) |
| **E6** | Reconfiguración de topología | Cambio de grafo en línea | 1 (determinista) |

**Reproducibilidad:** semilla fija declarada en el manifiesto de cada corrida. Todas las líneas base usan el mismo conjunto de semillas.

---

## 7. Métricas y gates

### 7.1 Gates de aceptación

| Gate | Métrica | Umbral | Origen |
|---|---|---|---|
| **G1** | $t_s$ a $\pm0.5\%$ | $\le T_f$ (52.54 s) | Cota calculada por el propio controlador |
| **G2** | $\Delta f_{p\text{-}p}$ | $< 0.200$ Hz | Solicitud S-14 |
| **G3** | $\max\lvert\eta_{Q,i} - \eta_{Q,j}\rvert$ | $< 0.020$ | `TEORIA.tex` |
| **G4** | $\max\lvert\eta_{P,i} - \eta_{P,j}\rvert$ | $< 0.020$ | `TEORIA.tex` |
| **G5** | $e_V$ | $\le \pm0.5\%$ | `10.3390/en16010517` ec. 12 |
| **G6** | $e_\omega$ | $\le \pm0.1$ Hz | `10.3390/en16010517` ec. 11 |
| **G7** | CFL | `verify_discrete_cfl_stability(0.5, 2)` = `True` | Propio controlador |
| **G8** | $\tau_{crit}$ | $\ge 100$ ms | `10.3390/app14030997` |

### 7.2 Métricas de reporte (no gates)

| Métrica | Definición | Nota |
|---|---|---|
| $t_s$ | A $\pm5\%$, $\pm1\%$ y $\pm0.5\%$ | **Decisión: se reportan las tres bandas; el gate se aplica en $\pm0.5\%$** |
| Sobreimpulso | $A_P, A_Q, A_\omega, A_V$ como % del escalón | `10.3390/en16010517` ec. 13–16 |
| Nadir | $\min_t \omega(t)$ en Hz | Reportar junto a NTC 1340 |
| RoCoF | $\max_t \lvert \dot{\omega}(t)\rvert$ en Hz/s | `10.1007/s40565-019-0565-y` |
| RMSE | $\sqrt{\text{mean}((x - x_{ref})^2)}$ | Declarar ventana y muestreo |
| Tasa de mensajes | msgs/s y bytes/s **absolutos** | No solo % de reducción |
| Trayectoria $\lvert e(t)\rvert$ | Serie temporal del error de consenso | Evidencia de monotonía |

### 7.3 Distinción obligatoria: norma ≠ objetivo de control

| Nivel | Frecuencia | Tensión | Fuente |
|---|---|---|---|
| **Protección** (NTC 1340) | $\pm2\%$ (58.8–61.2 Hz) | $\pm5\%$ | Norma colombiana |
| **Objetivo de control secundario** | $\pm0.1$ Hz | $\pm0.5\%$ | `10.3390/en16010517` |

**Cumplir la norma no acredita el objetivo de control.** Ambas se reportan por separado en toda tabla de resultados.

---

## 8. Controles negativos

**Obligatorios. Si alguno "pasa", el harness está roto y el benchmark no es válido.**

No hay práctica establecida de *negative controls* en benchmarks de control; el concepto se traslada de ML (*mutation testing*, *sanity checks*).

| ID | Falla inyectada | Resultado exigido |
|---|---|---|
| **N1** | Consenso anulado: `u = Σ(...) · 0` | **Debe detectar ausencia de restauración** — es exactamente el bug del v1 |
| **N2** | Ganancias ajenas (0.15 / 0.85 / 0.5 / 2.0) | **Debe dar $t_s > T_f$ o inestabilidad** |
| **N3** | Signo invertido en el término de consenso | **Debe divergir** |
| **N4** | Positivo: DAPI de Simpson-Porco | **Debe reproducir** su curva de referencia conocida |

---

## 9. Requisitos de reproducibilidad

Toda corrida registra, en un manifiesto verificable:

- Hash SHA-256 del controlador y de los inputs (topología, escenario, semillas)
- Versión de Python y de las dependencias
- Parámetros completos de cada controlador evaluado
- Semilla, condiciones iniciales y $\Delta t$
- Salida: CSV de telemetría + JSON de métricas

La reproducibilidad se verifica corriendo dos veces con la misma semilla y exigiendo **igualdad bit a bit** en las métricas.

---

## 10. Criterios de aceptación del benchmark

Antes de usarse para evaluar la tesis, el benchmark debe demostrar:

1. **Detecta un controlador roto** — N1, N2 y N3 reprochan como se especifica.
2. **Distingue clases** — FxTS supera a FTS en tiempo bajo condiciones iniciales extremas.
3. **Es reproducible** — dos corridas con la misma semilla dan resultado idéntico.
4. **No tiene umbrales mágicos** — todo gate deriva de una ecuación del manuscrito o se declara explícitamente como objetivo práctico.
5. **No reimplementa el artefacto** — el harness importa el controlador.

---

## 11. Fases de implementación

| Fase | Contenido | Responsable | Entregable |
|---|---|---|---|
| A | Investigación metodológica | `@investigador` | **Completada** |
| B | Esta especificación | HERMES | **Este documento** |
| C | Harness que importa el controlador real; reponer consenso; `T_max` desde la cota | `@encoder` | `run_benchmark.py` v2 |
| D | Controles negativos + barrido de sensibilidad | `@encoder` + HERMES | Informe de capacidad de detección |
| E | Corrida completa y valores canónicos con SHA-256 | `@encoder` | Tabla de valores de referencia |

**La Fase D no puede omitirse.** Sin controles negativos no se sabe si el benchmark mide o decora.

---

## 12. Trazabilidad de decisiones

| Decisión | Valor | Fecha |
|---|---|---|
| Alcance de red | Solo banco de 8 nodos | 2026-11-02 |
| CIGRE LV | Trabajo futuro, Cap. 6 — 40 barras y bus de 20 kV lo excluyen | 2026-11-02 |
| Sintonización | Publicada + optimizada, se reportan ambas | 2026-11-02 |
| Repeticiones | 1 corrida determinista; 100 semillas con p50/p95/p99 en E4 | 2026-11-02 |
| Bandas de $t_s$ | Reportar $\pm5\%$, $\pm1\%$, $\pm0.5\%$; gate en $\pm0.5\%$ | 2026-11-02 |

---

## 13. Referencias verificadas

| DOI | Uso en esta especificación |
|---|---|
| `10.3390/en16010517` | Definiciones de $e_\omega$, $e_V$, $t_s$, sobreimpulsos |
| `10.3390/en10091347` | Error de reparto de reactiva |
| `10.1049/stg2.12127` | Error relativo de Q por DER |
| `10.1109/TIE.2015.2436879` | Condición de reparto; DAPI como línea base |
| `10.1109/TIE.2010.2066534` | Droop y PI centralizado como líneas base |
| `10.3390/en14196266` | FTS frente a FxTS; distinción $T_f$ vs $t_s$ |
| `10.3390/app14030997` | Retardo crítico; tasa de mensajes |
| `10.1007/s40565-019-0565-y` | Nadir y RoCoF |
| `10.1049/stg2.12036` | Práctica de optimización de líneas base antes de comparar |
| `10.1109/TSG.2021.3067317` | Precedente de control secundario sobre CIGRE LV |
| `10.3390/eng7040147` | Conteo de 40 barras de CIGRE LV |

**Referencias no verificadas, declaradas:** Papathanassiou, Hatziargyriou & Strunz 2005 (CIGRE Symposium Atenas) y CIGRE TF C6.04.02 **no tienen DOI**; el conteo de barras se confirma en fuente secundaria. La métrica RMSE no tiene DOI canónico de microrred: es una métrica estadística estándar.
