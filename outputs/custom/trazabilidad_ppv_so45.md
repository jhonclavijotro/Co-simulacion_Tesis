# Entregable B (S-O-45) / E1 (S-O-49) · Traza Documental del $P_{PV}$ (Condición 4)

**Fecha:** 2026-11-19  
**Orden de trabajo:** S-O-45 (Parte B) / S-O-49 (Parte E1 · Cierre del Capítulo 8)  
**Estado:** `ENTREGADO PARA VERIFICACIÓN DE HERMES`  
**Documento maestro equivalente:** `notes/E1_traza_P_PV_SO49.md`

---

## 1. Declaración de los Cuatro Datos con Traza Directa a Archivo y Línea

| # | Dato Solicitado | Valor Declarado | Archivo y Línea Exacta en el Repositorio |
|---|---|---|---|
| **1** | **POA efectivo en la ventana de excedente (`[40, 120] s`) de `ESC-HIL-013`** | **$801{,}78\text{ W/m}^2$** media en ventana (mín. $800{,}89\text{ W/m}^2$ en $t=40{,}0\text{ s}$, máx. $802{,}67\text{ W/m}^2$ en $t=120{,}0\text{ s}$; $T_{\text{amb}} = 300{,}88\text{ K}$) | `Forms/escenarios_generados/ESC-HIL-013_excedente_con_espacio/datos_meteorologicos.csv:82-242` (`meta.json:80` registra `poa_ventana_W_m2: 800.89`) |
| **2** | **`N_inv` vigente en el código desplegado** | **`N_inv = 1`** | `Agents/node_dynamic_process.py:64-65` (`SistemaSolar(N_inv=1, ...)`; línea `:63` en commit `39de23e` de la serie del capítulo) y `Solar/SistemaSolar.py:22` (`def __init__(self, N_inv=1, ...)`) |
| **3** | **Estado del cálculo del MPP respecto de $V_{\text{array}}$ (`Solar/SistemaSolar.py`)** | **Usa $V_{\text{array}}$ real (NO $V_{\text{dcref}}$)** | `Solar/SistemaSolar.py:107` (`V_array = ctx["V_dc"] * (1.0 - ctx["duty_cycle"])`), `Solar/SistemaSolar.py:111` (`I_pv = self.panel.calculate_at_voltage(V_array, self.POA, self.Tam)`), `Solar/SistemaSolar.py:160` (`P_mpp = max(0.0, ctx["V_array"] * ctx["I_pv"]) * self.N_inv`; correspondía a `:134-139` en commit `39de23e`) |
| **4** | **Cifra canónica del $P_{PV}$ a ese POA** | **$2{,}175\text{ kW}$ AC** (media medida en corrida: $2{,}1756\text{ kW}$, rango $[2{,}1731,\; 2{,}1780]\text{ kW}$) | `outputs/custom/results/20261117T114647_ESC-HIL-013_excedente_con_espacio_seed42/telemetry_rack.csv` (columna `P2_kW` en $t \in [40{,}0,\; 120{,}0]\text{ s}$) y `Forms/escenarios_generados/ESC-HIL-016_excitacion_reactiva_180s/escenario.yaml:25` (`p_solar_ventana_kW: 2.175`) |

---

## 2. Resolución Explícita de la Discrepancia ($2{,}175\text{ kW}$ vs. $2{,}4214\text{ kW}$)

- **Cifra correcta (canónica):** **$2{,}175\text{ kW}$ AC** ($2{,}1756\text{ kW}$ medidos en telemetría de `ESC-HIL-013`).
- **Por qué los $2{,}4214\text{ kW}$ de `reporte_factibilidad.md` estaban mal:**
  1. En `Forms/escenarios_generados/ESC-HIL-013_excedente_con_espacio/reporte_factibilidad.md:13,39` (y heredado en `meta.json:81`), el cálculo previo al ensayo aplicó la fórmula analítica aproximada sobre la tensión nominal del bus DC:
     $$P_{mpp,\text{est}} = V_{\text{dcref}} \cdot I_{pv} \cdot N_{\text{inv}} = 400{,}0\text{ V} \times 6{,}0535\text{ A} \times 1 = 2{,}4214\text{ kW}$$
  2. Sin embargo, el código real ejecutado evalúa la corriente y potencia del arreglo fotovoltaico sobre la **tensión real del arreglo $V_{\text{array}} = V_{\text{dc}}(1 - D) \approx 359{,}0\text{ V}$** (`Solar/SistemaSolar.py:107,111,160`), inferior a $V_{\text{dcref}} = 400\text{ V}$.
  3. Evaluar con $V_{\text{dcref}} = 400\text{ V}$ introdujo un exceso analítico ficticio de $+246\text{ W}$ ($2{,}4214 - 2{,}1756 = +0{,}2458\text{ kW}$). Por tanto, **$2{,}4214\text{ kW}$ queda formalmente retirado** y **$2{,}175\text{ kW}$** se fija como la cifra canónica única del recurso solar para la ventana de excedente de la serie del Capítulo 8 (`ESC-HIL-001`–`ESC-HIL-028`).
