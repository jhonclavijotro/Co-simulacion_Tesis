# Entregable C (S-O-45) / E2 (S-O-49) · Tabla Canónica de Capacidad Firme (Condición 3)

**Fecha:** 2026-11-19  
**Orden de trabajo:** S-O-45 (Parte C) / S-O-49 (Parte E2 · Cierre del Capítulo 8)  
**Estado:** `ENTREGADO PARA VERIFICACIÓN DE HERMES`  
**Documento maestro equivalente:** `notes/E2_tabla_capacidad_firme_SO49.md`

---

## 1. Ecuación Formal y Declaración Explícita de Eficiencias

$$C_{\text{firm}} = P_{\text{diésel}}^{\text{eff}} + \eta_{\text{BESS}}\min\left(P_{\text{inv}},\; P_{\text{SoC}},\; P_{\text{dur}}\right)$$

Se declaran explícitamente las constantes efectivas ejecutadas por el código fuente desplegado:
- **$\eta_{\text{diésel}} = 1{,}0$** (`Agents/node_dynamic_process.py:80`, antes `:73`, `SistemaDiesel(P_nominal=10000.0, eta=1.0, ...)`).
- **$\eta_{\text{BESS}} = 1{,}0$** (modelo energético promedio del nodo en la serie `001`–`028`, `Pw = P_ref_eff`).
- **$P_{\text{inv,BESS}} = 3{,}000\text{ kW}$** (`p_max_W = 3000.0` desplegado en `Scripts/cluster_deployer.py:282` y `Scripts/run_rack_experiment_orchestrator.py:243`).

---

## 2. Tabla de Capacidad Firme por Recurso

| Recurso | $P_{\max}$ | $P_{\text{eff}}$ | SoC | $\eta$ | $t_d$ | Contribución | Fuente |
|---|---:|---:|:---:|:---:|:---:|---:|---|
| **Diésel N1** | $10{,}000\text{ kW}$ | $10{,}000\text{ kW}$ | n/a | **$1{,}0$** *(declarado)* | $\infty$ | **$10{,}000\text{ kW}$** | `Agents/node_dynamic_process.py:80` (antes `:73`), `Scripts/cluster_deployer.py:280`, `Scripts/run_rack_experiment_orchestrator.py:202` |
| **BESS N3** *(cond. $\text{SoC}_0 = 0{,}95$, `014`)* | $3{,}000\text{ kW}$ *(placa inv.)* | $P_{\text{inv}} = 3{,}000\text{ kW}$; $P_{\text{SoC}} = 20{,}000\text{ kW}$; $P_{\text{dur}}(4\text{h}) = 18{,}000\text{ kW}$ | $\text{SoC}_0 = 0{,}95$ ($\text{SoC}_{\min}=0{,}20$, $E_{\text{util}} = 72{,}0\text{ kWh}$ de $96{,}0\text{ kWh}$) | **$1{,}0$** *(declarado)* | $4{,}0\text{ h}$ eval. *(hasta $24{,}0\text{ h}$ @ $3\text{ kW}$)* | **$3{,}000\text{ kW}$** $\big(\min(3{,}000;\; 20{,}000;\; 18{,}000)\big)$ | `Scripts/cluster_deployer.py:282`, `Scripts/run_rack_experiment_orchestrator.py:243`, `BESS/SistemaBESS.py:25-26,39,70,104-131` |
| **BESS N3** *(cond. $\text{SoC}_0 = 0{,}50$, `008`/`010`/`013`)* | $3{,}000\text{ kW}$ *(placa inv.)* | $P_{\text{inv}} = 3{,}000\text{ kW}$; $P_{\text{SoC}} = 8{,}571\text{ kW}$; $P_{\text{dur}}(4\text{h}) = 7{,}200\text{ kW}$ | $\text{SoC}_0 = 0{,}50$ ($\text{SoC}_{\min}=0{,}20$, $E_{\text{util}} = 28{,}8\text{ kWh}$ de $96{,}0\text{ kWh}$) | **$1{,}0$** *(declarado)* | $4{,}0\text{ h}$ eval. *(hasta $9{,}6\text{ h}$ @ $3\text{ kW}$)* | **$3{,}000\text{ kW}$** $\big(\min(3{,}000;\; 8{,}571;\; 7{,}200)\big)$ | `ESC-HIL-013/meta.json:70`, `Scripts/cluster_deployer.py:282`, `BESS/SistemaBESS.py:25-26,39,70,104-131` |
| **Solar N2** | $5{,}000\text{ kW}$ *(placa inv.)* | $2{,}175\text{ kW}$ *(a $801{,}78\text{ W/m}^2$)* | n/a | — *(no despachable)* | $0{,}0\text{ h}$ | **$0{,}000\text{ kW}$** | `Scripts/cluster_deployer.py:281`, `Agents/node_dynamic_process.py:64-65`, `Solar/SistemaSolar.py:160` |
| **TOTAL ($C_{\text{firm}}$)** | **$18{,}000\text{ kW}$** | — | — | — | **$t_d \le 9{,}6\text{ h}$** ($\text{SoC}_0=0{,}50$) / **$24{,}0\text{ h}$** ($\text{SoC}_0=0{,}95$) | **$13{,}000\text{ kW}$** | $10{,}000 + 1{,}0 \cdot \min(P_{\text{inv}}, P_{\text{SoC}}, P_{\text{dur}})$ |

---

## 3. Picos Coincidentes Reales, Umbral de Déficit y Retiro del Déficit de $1{,}059\text{ kW}$

| Escenario | Pico Coincidente Real ($\max_t \sum P_i(t)$) | Suma No Coincidente *(descartada)* | Reserva Firme ($C_{\text{firm}} - P_{\text{pico,coinc}}$) | Margen de Reserva ($MR$) | Estado vs. Umbral |
|:---|---:|---:|---:|---:|:---:|
| **`ESC-HIL-003_consolidado_rev5`** *(Fase V §8.5: $12{,}594\text{ kW}$ @ $240\text{ s}$)* | **$12{,}9929\text{ kW}$** (@ $t=238{,}5\text{ s}$) | $13{,}2825\text{ kW}$ | **$+0{,}0071\text{ kW}$** (pico abs.) / **$+0{,}4060\text{ kW}$** (Fase V $12{,}594$) | **$+0{,}05\,\%$** / **$+3{,}22\,\%$** | **SIN DÉFICIT** |
| **`ESC-HIL-008_validacion_integrada`** *(Baseline canónico)* | **$11{,}5086\text{ kW}$** (@ $t=295{,}5\text{ s}$) | $11{,}8119\text{ kW}$ | **$+1{,}4914\text{ kW}$** | **$+12{,}96\,\%$** | **SIN DÉFICIT** |
| **`ESC-HIL-010_validacion_integrada_v2`** | **$6{,}5766\text{ kW}$** (@ $t=71{,}0\text{ s}$) | $6{,}6624\text{ kW}$ | **$+6{,}4234\text{ kW}$** | **$+97{,}67\,\%$** | **SIN DÉFICIT** |
| **`ESC-HIL-013` / `ESC-HIL-014`** | **$6{,}6752\text{ kW}$** (@ $t=14{,}5\text{ s}$) | $6{,}7615\text{ kW}$ | **$+6{,}3248\text{ kW}$** | **$+94{,}75\,\%$** | **SIN DÉFICIT** |

- **Umbral de déficit declarado:** $P_{\text{demanda,coincidente}} > \mathbf{13{,}000\text{ kW}}$ (con respaldo BESS para $t_d \le 9{,}6\text{ h}$) o $> \mathbf{10{,}000\text{ kW}}$ en contingencia $N-1$ sin BESS.
- **Dictamen sobre el déficit de $1{,}059\text{ kW}$ en §8.5 (`RESULTADOS.tex:293-300`):** **SE RETIRA FORMALMENTE.** Proviene de asumir $\eta = 0{,}95$ y $P_{\text{BESS}} = 1{,}5\text{ kW}$, constantes inexistentes en el código ejecutado ($\eta = 1{,}0$ y $p_{\max,\text{BESS}} = 3000\text{ W}$).
