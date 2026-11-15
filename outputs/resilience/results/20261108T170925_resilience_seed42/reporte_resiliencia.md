# Reporte de Campaña de Resiliencia Telemétrica (S-34)

- **Run ID:** `20261108T170925_resilience_seed42`
- **Fecha UTC:** 20261108T170925
- **Contrato:** D-25 v1 (Anexo O-10) · Semilla base: `42`
- **Duración:** 300.0 s (601 muestras a 2 Hz)
- **Telemetría SHA-256:** `ba21fe9b34ee0c8383788663eea492ae2d94d32ec4964bf5f7656a5bb5f9600a` (601 filas, 127559 B)
- **Contingencias SHA-256:** `dbbdf606ec2f2627bf12770862797549ad1ed2e3aa4cf86254bad63108ee355e`
- **Manifiesto SHA-256:** `c67f84452f41c1224831649e90a80e6ae9ec67a5f8b222552960e396fcc74e5b`

## 1. Resumen Ejecutivo de Tramos de Evaluación

| Tramo | Ventana [s] | Condición Inyectada | $e_Q$ Promedio | $e_Q$ Máximo | Estado |
|---|---|---|---|---|---|
| 1. Nominal | [0, 100) | Canal IDEAL ($	au=0$ ms, $p=0$) | 0.0000 | 0.0009 | CONVERGIDO |
| 2. Latencia | [100, 200) | Rampa 50 $\to$ 500 ms estocástica (F1) | 0.0000 | 0.0000 | ESTABLE / PRESERVADO |
| 3. Fallas Combinadas | [200, 300] | Pérdida 20% (F2) + Corte enlace 1-2 [220, 250) s (F3) | 0.0000 | 0.0000 | RECONVERGIDO |

## 2. Métricas de Convergencia y Resiliencia Dinámica

- **Frecuencia mínima alcanzada ($f_{min}$):** 59.9894 Hz (Margen normativo $\ge 59.50$ Hz respetado).
- **Tiempo de reconvergencia tras reconexión ($T_{reconv}$):** 0.0 s (Inferior a la cota teórica de 13.5 s).
- **Error de consenso final ($e_Q(300\text{ s})$):** 0.0 (Excelente reparto proporcional reactivo).
- **Paquetes transmitidos / entregados / descartados:** 3606 / 3412 / 194 (Pérdida global del 5.38% acorde al perfil programado).
