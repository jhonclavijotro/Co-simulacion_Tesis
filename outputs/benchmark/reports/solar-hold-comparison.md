# Experimento Nodal Independiente: Evaluación de Retenedores Multirate en Nodo Solar

**Fecha:** 2026-11-04T18:49:43.782472+00:00 · **ID Experimento:** `EXP-NODAL-SOLAR-HOLD`
**Referencia:** SIMULACION.md (S-24, S-26-2) · `TEORIA.tex:241`

### Hashes Criptográficos SHA-256 de Trazabilidad

| Componente | Archivo | Hash SHA-256 |
|---|---|---|
| `script_evaluador` | `solar_hold_nodal_benchmark.py` | `53e532678b01f9af603da5d6216f14a3db885003508833e3bf80f70a8d7b31fd` |
| `serie_temporal_csv` | `solar_hold_comparison.csv` | `40c9cfb43d3ba2abb5655ffa217a91de2b32c96e4cd67681df6b1b86e2aa8060` |
| `resultados_json` | `solar_hold_comparison.json` | `f725b82bbd0a17098e1dfafd2a05231a198ddb021c4baa495aff19f52b605d68` |

---

## 1. Tabla de Desempeño Comparativo (Perfil Canónico: Caída 0.2 p.u., $\tau = 4.5\text{ s}$)

| Retenedor | $\lambda$ | RMS [W] | Máximo [W] | Frente a ZOH |
|---|:---:|:---:|:---:|:---:|
| **ZOH** | `0.0` | **3.85** | **26.65** | **1.00x** |
| FROH (lambda=0.3) | `0.3` | 7.45 | 110.31 | 1.93x |
| FROH (lambda=0.5) | `0.5` | 10.80 | 166.09 | 2.80x |
| **FROH (lambda=0.7)** | `0.7` | **14.33** | **221.87** | **3.72x** |
| FROH (lambda=0.9) | `0.9` | 17.93 | 277.65 | 4.65x |
| FOH | `1.0` | 19.74 | 305.54 | 5.12x |

---

## 2. Hallazgos Científicos y Justificación Matemática

1. **Monotonía del Error:** El error de seguimiento de potencia activa $P_w$ crece monótonamente con $\lambda$:
   - **ZOH ($\lambda = 0.0$):** RMS $= 3.85\text{ W}$, Máximo $= 26.65\text{ W}$.
   - **FROH ($\lambda = 0.7$):** RMS $= 14.33\text{ W}$ ($3.72\times$ peor), Máximo $= 221.87\text{ W}$ ($8.32\times$ peor).
   - **FOH ($\lambda = 1.0$):** RMS $= 19.74\text{ W}$ ($5.12\times$ peor), Máximo $= 305.54\text{ W}$ ($11.46\times$ peor).
2. **Causa Física (Predictor Forward vs Interpolador):** En co-simulación causal en tiempo real,
   el algoritmo reconstruye la señal con la pendiente secante retrospectiva $(V(k)-V(k-1))/H$.
   En curvas convexas de relajación exponencial ($V(t) = 1 - \Delta V e^{-t/\tau}$), la pendiente secante
   pasada es estrictamente mayor que la derivada instantánea futura, sobrestimando sistemáticamente la tensión de excitación
   y desplazando el punto de máxima potencia (MPPT) del convertidor fotovoltaico.
3. **Inmunidad de DERs Despachables:** BESS y Diésel operan con inversores VSI donde la potencia inyectada
   $P_w = 1.5 V_d I_d = P_{\text{gen}}$ cancela algebraicamente la tensión de frontera, siendo inmunes al retenedor.
