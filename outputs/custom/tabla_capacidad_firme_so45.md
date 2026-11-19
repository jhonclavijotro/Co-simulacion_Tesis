# Entregable C (S-O-45) · Tabla Canónica de Capacidad Firme (Condición 3)

**Fecha:** 2026-11-19  
**Orden de trabajo:** S-O-45 (Parte C — Condición 3)  
**Estado:** `ENTREGADO PARA VERIFICACIÓN`  
**Alcance:** Contabilidad auditable de capacidad firme ($C_{\text{firm}}$) basada estrictamente en las constantes desplegadas en el código fuente vigente, declaración del umbral de déficit y retiro formal del déficit de $1{,}059\text{ kW}$ de §8.5.

---

## 1. Ecuación Formal y Constantes Desplegadas

La capacidad firme total despachable de la microrred en operación en isla se define como:

$$C_{\text{firm}} = P_{\text{diésel}}^{\text{eff}} + \eta_{\text{BESS}} \min\left(P_{\text{inv}},\; P_{\text{SoC}},\; P_{\text{dur}}\right)$$

Las constantes efectivas verificadas directamente en el código ejecutado son:
- **Diésel (Nodo 1):** `P_nominal = 10000.0 W` y `eta = 1.0` (`Agents/node_dynamic_process.py:73`).
- **Solar PV (Nodo 2):** `N_inv = 1` (`Agents/node_dynamic_process.py:63`), `p_max_W = 5000.0 W` (`Scripts/cluster_deployer.py:281`), excluido de capacidad firme por intermitencia ($CF = 0$).
- **BESS (Nodo 3):** `p_max_W = 3000.0 W` (`Scripts/run_rack_experiment_orchestrator.py:243`, `Scripts/cluster_deployer.py:282`, `Agents/node_dynamic_process.py:196`) y eficiencia nodal $\eta_{\text{BESS}} = 1{,}0$ (`BESS/SistemaBESS.py:199`, `ctx["Pw"] = P_ref_eff`).

---

## 2. Tabla Canónica de Capacidad Firme por Recurso

| Recurso DER | $P_{\max}$ Placa (kW) | $P_{\text{eff}}$ (kW) | Estado de Carga ($\text{SoC}$) | Eficiencia $\eta$ | Duración $t_d$ | Contribución Firme (kW) | Fuente del Dato (Archivo y Línea) |
|---|---|---|---|---|---|---|---|
| **Generador Diésel (N1)** | $10{,}000$ | $10{,}000$ | N/A (combustible continuo) | $1{,}00$ | $\infty$ (continuo) | **$10{,}000$** | `Agents/node_dynamic_process.py:73` (`P_nominal=10000.0, eta=1.0`); `Scripts/run_rack_experiment_orchestrator.py:202`; `Scripts/cluster_deployer.py:280` |
| **Solar Fotovoltaico (N2)** | $5{,}000$ | $2{,}175$ (a $801{,}78\text{ W/m}^2$) | N/A (recurso variable) | — | $0{,}0\text{ h}$ (no despachable) | **$0{,}000$** | `Agents/node_dynamic_process.py:63` (`N_inv=1`); `Solar/SistemaSolar.py:139`; `Scripts/cluster_deployer.py:281` |
| **Sistema BESS (N3)** | $3{,}000$ | $P_{\text{inv}} = 3{,}000$ ($P_{\text{SoC}} = 8{,}571$ a $\text{SoC}_0$) | $\text{SoC}_0 = 0{,}50$, $\text{SoC}_{\min} = 0{,}20$ ($E_{\text{util}} = 28{,}8\text{ kWh}$ de $96{,}0\text{ kWh}$) | $1{,}00$ | $9{,}6\text{ h}$ a $3{,}0\text{ kW}$ ($P_{\text{dur}} \ge 3{,}0\text{ kW}$ para $t_d \le 9{,}6\text{ h}$) | **$3{,}000$** | `Scripts/run_rack_experiment_orchestrator.py:243` (`--p-max 3000.0`); `Scripts/cluster_deployer.py:282`; `Agents/node_dynamic_process.py:196`; `BESS/SistemaBESS.py:25-28,101-110,199` |
| **Capacidad Firme Total ($C_{\text{firm}}$)** | **$18{,}000$** | — | — | — | Hasta $9{,}6\text{ h}$ ($10{,}000\text{ kW}$ para $t_d > 9{,}6\text{ h}$) | **$13{,}000\text{ kW}$** | $10{,}000 + 1{,}0 \cdot \min(3{,}000,\; 8{,}571,\; P_{\text{dur}})$ |

### Detalle de Cómputo del Término BESS
- **Energía nominal del banco (`BESS/SistemaBESS.py:25-28`):** $V_{\text{pack}} = 48{,}0\text{ V} \times 10 = 480{,}0\text{ V}$; capacidad $200{,}0\text{ Ah}$; $E_{\text{nom}} = 480{,}0\text{ V} \times 200{,}0\text{ Ah} = 96{,}0\text{ kWh}$.
- **Energía utilizable en descarga:** Con $\text{SoC}_0 = 0{,}50$ (`Agents/node_dynamic_process.py:59`) y $\text{SoC}_{\min} = 0{,}20$ (`BESS/SistemaBESS.py:102`):
  $$E_{\text{util}} = (0{,}50 - 0{,}20) \times 96{,}0\text{ kWh} = 28{,}8\text{ kWh}$$
- **Cota por estado de carga (`BESS/SistemaBESS.py:104-110`):** Con $p_{\text{base}} = V_{\text{dcref}} \cdot I_{\text{inv,max}} = 400 \times 50 = 20{,}000\text{ kW}$:
  $$P_{\text{SoC}} = 20{,}000 \cdot \frac{0{,}50 - 0{,}20}{0{,}90 - 0{,}20} = 8{,}571\text{ kW}$$
- **Cota por duración:** $P_{\text{dur}}(t_d) = \frac{28{,}8\text{ kWh}}{t_d}$. Para cualquier ventana $t_d \le 9{,}6\text{ h}$ (incluyendo todas las corridas HIL de $180\text{ s}$ a $600\text{ s}$), $P_{\text{dur}} \ge 3{,}000\text{ kW}$.
- **Mínimo efectivo del BESS:** $\min(3{,}000,\; 8{,}571,\; P_{\text{dur}}) = \mathbf{3{,}000\text{ kW}}$, luego $\eta_{\text{BESS}} \cdot 3{,}000 = \mathbf{3{,}000\text{ kW}}$.

---

## 3. Aritmética del Umbral de Déficit y Retiro del Déficit de $1{,}059\text{ kW}$ (§8.5)

1. **Umbrales formales de déficit:**
   - **Operación normal con respaldo BESS ($t_d \le 9{,}6\text{ h}$, $\text{SoC} \in (0{,}20,\; 0{,}95]$):** Se declara déficit únicamente si $P_{\text{demanda}} > \mathbf{13{,}000\text{ kW}}$.
   - **Contingencia $N-1$ sin BESS (solo Diésel):** Se declara déficit únicamente si $P_{\text{demanda}} > \mathbf{10{,}000\text{ kW}}$.

2. **Contrastación aritmética frente a las demandas del estudio:**
   - **Frente a la demanda pico histórica citada en §8.5 ($12{,}594\text{ kW}$):**
     $$\Delta P_{\text{cap}} = C_{\text{firm}} - P_{\text{demanda,max}} = 13{,}000\text{ kW} - 12{,}594\text{ kW} = \mathbf{+0{,}406\text{ kW}} \quad (+3{,}22\,\% \text{ de superávit firme, incluso con } P_{PV} = 0)$$
   - **Frente a la demanda pico coincidente de los escenarios consolidados (`ESC-HIL-013/014/016`, $P_{\text{pico,coinc}} = 7{,}3697\text{ kW}$):**
     $$\Delta P_{\text{cap}} = 13{,}000\text{ kW} - 7{,}370\text{ kW} = \mathbf{+5{,}630\text{ kW}} \quad (+76{,}39\,\% \text{ de margen de reserva firme})$$

3. **Resolución formal sobre §8.5:**
   - El déficit de **$-1{,}059\text{ kW}$** reportado originalmente en §8.5 provenía de asumir $\eta_{\text{diésel}} = 0{,}95$ ($9{,}5\text{ kW}$) y $P_{\text{BESS}} = 1{,}5\text{ kW}$ ($9{,}5 + 1{,}5 + 0{,}535 = 11{,}535\text{ kW} < 12{,}594\text{ kW}$).
   - Dichos parámetros **no corresponden** al código ejecutado (`eta = 1.0` y `p_max = 3000.0 W`). Con las constantes vigentes, $C_{\text{firm}} = 13{,}000\text{ kW} > 12{,}594\text{ kW}$, por lo que **no existe déficit de capacidad firme**. La cifra de $1{,}059\text{ kW}$ queda formalmente **retirada**.
