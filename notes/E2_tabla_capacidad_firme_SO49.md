# E2 (S-O-49) · Tabla Canónica de Capacidad Firme (Entregable Bloqueante)

**Fecha:** 2026-11-19  
**Orden de trabajo:** S-O-49 (Parte E2 · Cierre del Capítulo 8)  
**Estado:** `ENTREGADO PARA VERIFICACIÓN DE HERMES`  
**Alcance:** Recuento auditable de capacidad firme ($C_{\text{firm}}$) bajo las constantes reales desplegadas en el código de la serie del Capítulo 8 (`ESC-HIL-001`–`ESC-HIL-028`), evaluación con picos coincidentes reales, declaración aritmética del umbral de déficit y retiro explícito del déficit de $1{,}059\text{ kW}$ de §8.5. *(El modelo de inversor RL + bus DC de `029` queda fuera del alcance del capítulo).*

---

## 1. Fórmula Formal y Declaración Explícita de Eficiencias

La capacidad firme total despachable de la microrred en isla se rige por:

$$C_{\text{firm}} = P_{\text{diésel}}^{\text{eff}} + \eta_{\text{BESS}}\min\left(P_{\text{inv}},\; P_{\text{SoC}},\; P_{\text{dur}}\right)$$

Se declaran explícitamente las constantes efectivas ejecutadas por el código fuente desplegado (en lugar de las constantes asumidas en el borrador previo de §8.5):
- **$\eta_{\text{diésel}} = 1{,}0$** (declarado explícitamente: `Agents/node_dynamic_process.py:80`, antes `:73`, `SistemaDiesel(P_nominal=10000.0, eta=1.0, ...)` — *no* $0{,}95$).
- **$\eta_{\text{BESS}} = 1{,}0$** (declarado explícitamente para el modelo energético promedio de la serie del capítulo `001`–`028` antes de S-O-48B, `Pw = P_ref_eff` — *no* $0{,}95$).
- **$P_{\text{inv,BESS}} = 3{,}000\text{ kW}$** (`p_max_W = 3000.0` desplegado en `Scripts/cluster_deployer.py:282` y `Scripts/run_rack_experiment_orchestrator.py:243` — *no* $1{,}500\text{ kW}$).

---

## 2. Tabla de Capacidad Firme por Recurso

| Recurso | $P_{\max}$ | $P_{\text{eff}}$ | SoC | $\eta$ | $t_d$ | Contribución | Fuente |
|---|---:|---:|:---:|:---:|:---:|---:|---|
| **Diésel N1** | $10{,}000\text{ kW}$ | $10{,}000\text{ kW}$ | n/a | **$1{,}0$** *(declarado)* | $\infty$ (combustible continuo) | **$10{,}000\text{ kW}$** | `Agents/node_dynamic_process.py:80` (antes `:73`, `P_nominal=10000.0, eta=1.0`), `Scripts/cluster_deployer.py:280`, `Scripts/run_rack_experiment_orchestrator.py:202` |
| **BESS N3** *(cond. $\text{SoC}_0 = 0{,}95$, `014`)* | $3{,}000\text{ kW}$ *(placa inv.)* | $P_{\text{inv}} = 3{,}000\text{ kW}$; $P_{\text{SoC}} = 20{,}000\text{ kW}$; $P_{\text{dur}}(4\text{h}) = 18{,}000\text{ kW}$ | $\text{SoC}_0 = 0{,}95$ ($\text{SoC}_{\min}=0{,}20$, $E_{\text{util}} = 72{,}0\text{ kWh}$ de $96{,}0\text{ kWh}$) | **$1{,}0$** *(declarado)* | $4{,}0\text{ h}$ eval. *(cota $3\text{ kW}$ sostenida hasta $24{,}0\text{ h}$)* | **$3{,}000\text{ kW}$** $\big(\min(3{,}000;\; 20{,}000;\; 18{,}000)\big)$ | `Scripts/cluster_deployer.py:282`, `Scripts/run_rack_experiment_orchestrator.py:243` (`3000.0 W`), `BESS/SistemaBESS.py:25-26,39,70,104-131` |
| **BESS N3** *(cond. $\text{SoC}_0 = 0{,}50$, `008`/`010`/`013`)* | $3{,}000\text{ kW}$ *(placa inv.)* | $P_{\text{inv}} = 3{,}000\text{ kW}$; $P_{\text{SoC}} = 8{,}571\text{ kW}$; $P_{\text{dur}}(4\text{h}) = 7{,}200\text{ kW}$ | $\text{SoC}_0 = 0{,}50$ ($\text{SoC}_{\min}=0{,}20$, $E_{\text{util}} = 28{,}8\text{ kWh}$ de $96{,}0\text{ kWh}$) | **$1{,}0$** *(declarado)* | $4{,}0\text{ h}$ eval. *(cota $3\text{ kW}$ sostenida hasta $9{,}6\text{ h}$)* | **$3{,}000\text{ kW}$** $\big(\min(3{,}000;\; 8{,}571;\; 7{,}200)\big)$ | `ESC-HIL-013/meta.json:70` (`soc_inicial: 0.5`), `Scripts/cluster_deployer.py:282`, `BESS/SistemaBESS.py:25-26,39,70,104-131` |
| **Solar N2** | $5{,}000\text{ kW}$ *(placa inv.)* | $2{,}175\text{ kW}$ *(a $801{,}78\text{ W/m}^2$)* | n/a | — *(no despachable)* | $0{,}0\text{ h}$ *(intermitente, $CF=0$)* | **$0{,}000\text{ kW}$** | `Scripts/cluster_deployer.py:281`, `Agents/node_dynamic_process.py:64-65` (`N_inv=1`), `Solar/SistemaSolar.py:160` (ver E1) |
| **TOTAL ($C_{\text{firm}}$)** | **$18{,}000\text{ kW}$** | — | — | — | **$t_d \le 9{,}6\text{ h}$** ($\text{SoC}_0=0{,}50$) / **$24{,}0\text{ h}$** ($\text{SoC}_0=0{,}95$) | **$13{,}000\text{ kW}$** | $10{,}000 + 1{,}0 \cdot \min(P_{\text{inv}}, P_{\text{SoC}}, P_{\text{dur}})$ |

### Aritmética del Mínimo del BESS (No se cuenta la placa directamente sin verificar $P_{\text{SoC}}$ y $P_{\text{dur}}$)
1. **Energía del banco (`BESS/SistemaBESS.py:25-26,39`):** $V_{\text{pack}} = 48{,}0\text{ V} \times 10 = 480{,}0\text{ V}$, capacidad $200{,}0\text{ Ah} \implies E_{\text{nom}} = 480{,}0 \times 200{,}0 = 96{,}0\text{ kWh}$.
2. **Potencia base del modelo de batería (`BESS/SistemaBESS.py:70,104-112`):** $p_{\text{base}} = V_{\text{dcref}} \cdot I_{\text{inv,max}} = 400 \times 50 = 20{,}000\text{ kW}$, acotado en descarga linealmente entre $\text{SoC}_{\min} = 0{,}20$ y $\text{SoC}_{\max} = 0{,}90$:
   - Para $\text{SoC} = 0{,}95$: $P_{\text{SoC}} = 20{,}000\text{ kW}$, $E_{\text{util}} = 0{,}75 \times 96{,}0 = 72{,}0\text{ kWh} \implies P_{\text{dur}}(t_d = 4\text{ h}) = 18{,}000\text{ kW}$.
   - Para $\text{SoC} = 0{,}50$: $P_{\text{SoC}} = 20{,}000 \cdot \frac{0{,}50 - 0{,}20}{0{,}90 - 0{,}20} = 8{,}571\text{ kW}$, $E_{\text{util}} = 0{,}30 \times 96{,}0 = 28{,}8\text{ kWh} \implies P_{\text{dur}}(t_d = 4\text{ h}) = 7{,}200\text{ kW}$.
3. **Evaluación de la fórmula:** En ambas condiciones ($\text{SoC}_0 = 0{,}95$ y $\text{SoC}_0 = 0{,}50$), tanto $P_{\text{SoC}}$ como $P_{\text{dur}}$ superan la potencia nominal del inversor desplegado ($P_{\text{inv}} = 3{,}000\text{ kW}$), resultando $\min(P_{\text{inv}}, P_{\text{SoC}}, P_{\text{dur}}) = 3{,}000\text{ kW}$ y **$C_{\text{firm}} = 13{,}000\text{ kW}$**. *(Nota de sensibilidad: en contingencia $N-1$ sin BESS o para autonomías $t_d > 9{,}6\text{ h}$ desde $\text{SoC}_0=0{,}50$, la capacidad firme se reduce únicamente al Diésel: $10{,}000\text{ kW}$).*

---

## 3. Picos Coincidentes Reales, Umbral de Déficit y Margen de Reserva

Todos los valores de demanda se calculan directamente como el **máximo temporal coincidente** $\max_t \sum_{i=4}^8 P_i(t)$ en cada `datos_demanda.csv` (se descarta la suma de máximos individuales no coincidentes):

| Escenario | Pico Coincidente Real ($\max_t \sum P_i(t)$) | Suma No Coincidente *(descartada)* | Reserva Firme ($C_{\text{firm}} - P_{\text{pico,coinc}}$) | Margen de Reserva ($MR$) | Estado vs. Umbral |
|:---|---:|---:|---:|---:|:---:|
| **`ESC-HIL-003_consolidado_rev5`** *(Fase V §8.5: $12{,}594\text{ kW}$ @ $240\text{ s}$)* | **$12{,}9929\text{ kW}$** (@ $t=238{,}5\text{ s}$) | $13{,}2825\text{ kW}$ | **$+0{,}0071\text{ kW}$** (sobre pico abs.) / **$+0{,}4060\text{ kW}$** (sobre Fase V $12{,}594$) | **$+0{,}05\,\%$** / **$+3{,}22\,\%$** | **SIN DÉFICIT** |
| **`ESC-HIL-008_validacion_integrada`** *(Baseline canónico)* | **$11{,}5086\text{ kW}$** (@ $t=295{,}5\text{ s}$) | $11{,}8119\text{ kW}$ | **$+1{,}4914\text{ kW}$** | **$+12{,}96\,\%$** | **SIN DÉFICIT** |
| **`ESC-HIL-010_validacion_integrada_v2`** | **$6{,}5766\text{ kW}$** (@ $t=71{,}0\text{ s}$) | $6{,}6624\text{ kW}$ | **$+6{,}4234\text{ kW}$** | **$+97{,}67\,\%$** | **SIN DÉFICIT** |
| **`ESC-HIL-013` / `ESC-HIL-014`** | **$6{,}6752\text{ kW}$** (@ $t=14{,}5\text{ s}$) | $6{,}7615\text{ kW}$ | **$+6{,}3248\text{ kW}$** | **$+94{,}75\,\%$** | **SIN DÉFICIT** |

### Declaración Formal del Umbral de Déficit y Retiro del Déficit de $1{,}059\text{ kW}$ (§8.5)
1. **Umbral de déficit declarado (con respaldo BESS):** Se produce déficit de capacidad firme únicamente cuando:
   $$P_{\text{demanda,coincidente}} > C_{\text{firm}} = \mathbf{13{,}000\text{ kW}}$$
   *(Con déficit energético previo si se exige $t_d > 9{,}6\text{ h}$ continuas a $3\text{ kW}$ desde $\text{SoC}_0 = 0{,}50$, o en contingencia $N-1$ sin BESS donde el umbral desciende a $10{,}000\text{ kW}$).*
2. **Dictamen sobre el déficit de $1{,}059\text{ kW}$ en §8.5 (`RESULTADOS.tex:293-300`):** **SE RETIRA FORMALMENTE.** El texto actual de `RESULTADOS.tex:293-300` calculó $P_{\text{firme}} = 9{,}5 + 1{,}5 + 0{,}535 = 11{,}535\text{ kW}$ y dedujo $\Delta P = 11{,}535 - 12{,}594 = -1{,}059\text{ kW}$ asumiendo $\eta_{\text{diésel}} = 0{,}95$ y $P_{\text{BESS}} = 1{,}5\text{ kW}$. Bajo las constantes reales del código desplegado ($\eta = 1{,}0$ y $p_{\max,\text{BESS}} = 3000\text{ W}$), la capacidad firme es **$13{,}000\text{ kW}$**: frente a la demanda de la Fase V ($12{,}594\text{ kW}$) existe un superávit firme de **$+0{,}406\text{ kW}$ ($+3{,}22\,\%$)** incluso excluyendo la generación fotovoltaica ($P_{PV}=0$).
