# Entregable B (S-O-45) · Trazabilidad Documental del $P_{PV}$ (Condición 4)

**Fecha:** 2026-11-19  
**Orden de trabajo:** S-O-45 (Parte B — Condición 4)  
**Estado:** `ENTREGADO PARA VERIFICACIÓN`  
**Alcance:** Declaración auditable de la cifra canónica de potencia fotovoltaica ($P_{PV}$) del modelo vigente y resolución de la discrepancia entre `reporte_factibilidad.md` ($2{,}4214\text{ kW}$) y la telemetría de corrida ($2{,}1756\text{ kW}$).

---

## 1. Declaración Formal de los Cuatro Parámetros Auditados

| # | Parámetro Solicitado | Valor Declarado | Fuente y Ubicación Exacta en el Repositorio |
|---|---|---|---|
| **(i)** | **POA efectivo en la ventana de excedente (`[40, 120] s`)** | **$801{,}78\text{ W/m}^2$** promedio (mínimo $800{,}89\text{ W/m}^2$ en $t=40{,}0\text{ s}$, máximo $802{,}67\text{ W/m}^2$ en $t=120{,}0\text{ s}$; $T_{\text{amb}} = 300{,}88\text{ K}$) | `Forms/escenarios_generados/ESC-HIL-013_excedente_con_espacio/datos_meteorologicos.csv` (columnas `N2_POA_W_m2`, `N2_T_amb_K`, filas correspondientes a `tiempo_s` $\in [40{,}0,\; 120{,}0]$) |
| **(ii)** | **`N_inv` vigente** | **`N_inv = 1`** | `Agents/node_dynamic_process.py:63` (`self.model = SistemaSolar(N_inv=1)`) y `Solar/SistemaSolar.py:22` (`def __init__(self, N_inv=1, ...)`) |
| **(iii)** | **¿MPP corregido sobre $V_{\text{array}}$ aplicado?** | **SÍ aplicado** (`V_array = V_dc * (1 - D)`) | `Solar/SistemaSolar.py:93-100` y `Solar/SistemaSolar.py:137-139` (`P_mpp = max(0.0, ctx["V_array"] * ctx["I_pv"]) * self.N_inv`) |
| **(iv)** | **Cifra canónica de $P_{PV}$ para recuentos de capacidad** | **$2{,}175\text{ kW}$ AC** (media medida en corrida: $2{,}1756\text{ kW}$, rango $[2{,}1731,\; 2{,}1780]\text{ kW}$) | `outputs/custom/results/20261117T114647_ESC-HIL-013_excedente_con_espacio_seed42/telemetry_rack.csv` (columna `P2_kW` en $t \in [40{,}0,\; 120{,}0]\text{ s}$) y `Forms/escenarios_generados/ESC-HIL-016_excitacion_reactiva_180s/escenario.yaml:25` (`p_solar_ventana_kW: 2.175`) |

---

## 2. Explicación Técnica de la Discrepancia ($2{,}4214\text{ kW}$ vs. $2{,}1756\text{ kW}$)

1. **Cifra del `reporte_factibilidad.md` de `ESC-HIL-013/014` ($2{,}4214\text{ kW}$):**
   - En `Forms/escenarios_generados/ESC-HIL-013_excedente_con_espacio/reporte_factibilidad.md:39` se calculó una estimación analítica previa utilizando la tensión de referencia del bus DC ($V_{\text{dcref}} = 400\text{ V}$):
     $$P_{mpp,\text{est}} = V_{\text{dcref}} \cdot I_{pv} \cdot N_{\text{inv}} = 2{,}4214\text{ kW}$$
   - Esta expresión sobreestima la potencia disponible del arreglo al evaluar $I_{pv}$ sobre $V_{\text{dcref}} = 400\text{ V}$ en lugar de la tensión real del arreglo fotovoltaico $V_{\text{array}} < V_{\text{dc}}$.

2. **Modelo ejecutado en el código fuente (`Solar/SistemaSolar.py`):**
   - En `Solar/SistemaSolar.py:93`, el convertidor Boost fija la tensión real del arreglo fotovoltaico como:
     $$V_{\text{array}} = V_{\text{dc}} \cdot (1 - D)$$
   - La corriente del panel `I_pv` se evalúa en la curva I–V a esa tensión $V_{\text{array}}$ (`Solar/SistemaSolar.py:97`) y la potencia MPP disponible se calcula sobre `V_array` (`Solar/SistemaSolar.py:139`):
     $$P_{mpp} = \max(0{,}0,\; V_{\text{array}} \cdot I_{pv}) \cdot N_{\text{inv}}$$
   - Al atravesar las etapas Boost e inversor conectado a red (`Solar/SistemaSolar.py:128-135`), la potencia activa AC real entregada al PCC en el nodo 2 durante la ventana `[40, 120] s` de `ESC-HIL-013` es **$2{,}1756\text{ kW}$ AC**.

---

## 3. Declaración de Uso Canónico en el Manuscrito

- Para todos los recuentos de capacidad, balances de holgura de excedente y redacción del Capítulo 8 bajo la ventana meteorológica de referencia ($\text{POA}_{\text{medio}} = 801{,}78\text{ W/m}^2$, $T_{\text{amb}} = 300{,}88\text{ K}$, `N_inv = 1`), la cifra canónica oficial es **$P_{PV} = 2{,}175\text{ kW}$ AC**.
- Se retira de los balances la cifra analítica previa de $2{,}4214\text{ kW}$ por provenir de una aproximación sin corrección por $V_{\text{array}}$.
