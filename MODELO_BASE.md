# Modelo Base: Co-simulación Multi-Agente de una Microrred Eléctrica

## 1. Descripción General

Este proyecto implementa un sistema de **co-simulación multi-agente (MAS)** de una microrred eléctrica radial de baja tensión (110 V). El sistema integra modelos dinámicos de generación (BESS, Solar, Eólica, Hidroeléctrica, Diésel), cargas y un solucionador de flujo de potencia en un bucle de co-simulación sincronizado por un reloj maestro.

El objetivo es evaluar estrategias de control distribuido (consenso, LVRT, regulación de tensión y frecuencia) bajo condiciones cuasi-estáticas con paso fijo de 0.1 s.

### 1.1 Arquitectura de Capas

```
┌─────────────────────────────────────────────────────────────────────┐
│                    CAPA DE COORDINACIÓN                             │
│  PC Central (server_pc.py / test_sim_1hora.py)                     │
│  ┌─────────────┐  ┌──────────────────┐  ┌───────────────────────┐  │
│  │ RelojZMQ     │  │ MasterClock      │  │ ForwardBackwardSweep  │  │
│  │ (TCP server) │──│ (bucle temporal) │──│ (solver FBS)          │  │
│  │ puerto 5000  │  │ paso = 0.1 s    │  │ V = f(P, Q)          │  │
│  └──────┬───────┘  └──────────────────┘  └───────────────────────┘  │
└─────────┼───────────────────────────────────────────────────────────┘
          │ TCP/JSON (ZMQ protocol)
          │ tick → medicion  (puerto 5000)
    ┌─────┴──────────────┬─────────────────────┐
    ▼                    ▼                     ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────────┐
│ CAPA AGENTE  │  │ CAPA AGENTE  │  │ CAPA AGENTE       │
│ BESS (PC)    │  │ Solar (RPi)  │  │ Diesel/Eol/Hid    │
│ id=1, nodo=1 │  │ id=2, nodo=3 │  │ (PC / remoto)     │
│ ┌──────────┐ │  │ ┌──────────┐ │  │ ┌──────────────┐  │
│ │BateriaSim-│ │  │ │SolarSim- │ │  │ │SistemaDiesel│  │
│ │plificada  │ │  │ │plificado │ │  │ │SistemaHidri-│  │
│ └──────────┘ │  │ └──────────┘ │  │ │co           │  │
└──────────────┘  └──────────────┘  │ │SistemaEolic-│  │
                                    │ │o           │  │
                                    │ │SistemaSolar │  │
                                    │ └──────────────┘  │
                                    └──────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ CAPA DE DINÁMICA REMOTA (Opcional, TCP puerto 6000)                │
│ ServicioDinamica (servicio_dinamica.py)                             │
│ Expone modelos detallados (SistemaBESS, SistemaDiesel, etc.)       │
│ como servicio TCP independiente para separación de procesos        │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Elementos del Experimento

### 2.1 Red de Distribución

Archivo: `CentralPC/red_5nodos.csv`

```
Slack ── BESS ── Carga_1 ── Solar ── Carga_2
 Nodo 0    Nodo 1   Nodo 2    Nodo 3    Nodo 4
```

| Rama | Desde | Hasta | R (Ω) | X (Ω) | Longitud (m) |
|------|-------|-------|-------|-------|-------------|
| 1    | 0     | 1     | 0.05  | 0.02  | 100 |
| 2    | 1     | 2     | 0.04  | 0.015 | 80 |
| 3    | 2     | 3     | 0.06  | 0.025 | 120 |
| 4    | 3     | 4     | 0.04  | 0.015 | 80 |

Parámetros base:
- **V_base** = 110 V (todos los nodos)
- **S_base** = 10 kVA
- **Relación R/X** ≈ 2.5 (red de distribución típica)

### 2.2 Componentes de Generación y Carga

#### 2.2.1 BESS (Battery Energy Storage System)

| Parámetro | Valor | Archivo |
|-----------|-------|---------|
| Potencia nominal | 5 kW | `MAS/BESS_simplificado.py` |
| Tensión pack | 480 V (48 V × 10 serie) | `BateriaSimplificada.__init__()` |
| Capacidad | 100 Ah | |
| SoC inicial | 50 % | |
| η_carga | 0.92 | |
| η_descarga | 0.95 | |
| Algoritmo de control | Consenso por SoC (K_soc = 2.0) | `_loop_agente()` en `ejecutar_agente.py` |
| LVRT | Derating lineal si V_pcc < 0.88 pu | `BESS_simplificado.py:35-41` |

**Ecuación de potencia:**

$$P_{ref,i} = \frac{P_{demanda}}{N} + K_{soc} \cdot (SoC_i - \overline{SoC})$$

$$SoC_{i+1} = SoC_i - \frac{P_{real} \cdot \eta^{\pm 1} \cdot \Delta t}{E_{wh} \cdot 3600}$$

#### 2.2.2 Solar

| Parámetro | Valor | Archivo |
|-----------|-------|---------|
| Potencia pico | 3 kW | `Solar/SolarSimplificado.py` |
| Perfil | Gaussiano: $P(t) = 3000 \cdot e^{-((t-1800)/600)^2}$ | `_perfil_potencia()` |
| LVRT | $V_{pcc} < 0.5 \rightarrow 0$; $0.5 \leq V_{pcc} < 0.88 \rightarrow$ derating | `SolarSimplificado.step():40-44` |

#### 2.2.3 Cargas

| Nodo | P (W) | Q (VAR) | fp |
|------|-------|---------|-----|
| 2 (Carga 1) | 2000 | 657 | 0.95 |
| 4 (Carga 2) | 1500 | 493 | 0.95 |

Modelo de carga: **PQ constante** (el solver FBS las trata como inyecciones de potencia constante).

#### 2.2.4 Otros Modelos (disponibles en la fábrica)

| Modelo | Archivo | Descripción |
|--------|---------|-------------|
| SistemaDiesel | `Diesel/SistemaDiesel.py` | Generador síncrono con gobernador PI |
| SistemaHidrico | `Hidrica/SistemaHidrico.py` | Turbina hidroeléctrica con regulación de caudal |
| SistemaEolico | `Eolica/SistemaEolico.py` | Turbina eólica con MPPT |
| SistemaSolar (detallado) | `Solar/SistemaSolar.py` | Panel + Boost + Inversor + PI Vdc |

Todos los modelos comparten la interfaz `step(dt, P_ref, V_pcc=None)`.

---

## 3. Conectividad y Flujo de Información

### 3.1 Protocolo de Comunicación (ZMQ sobre TCP)

La comunicación entre el servidor central y los agentes utiliza **TCP sockets con mensajes JSON delimitados por `\n`** (no utiliza la biblioteca ZeroMQ real, el nombre ZMQ es histórico). Cada mensaje es un objeto JSON de una línea terminada en salto de línea.

#### 3.1.1 Handshake

```
Agente ────{"tipo": "hello", "id": N}─────────▶ Servidor
```

El servidor registra al agente y lo incluye en el ciclo de ticks.

#### 3.1.2 Tick (Servidor → Agentes)

```json
{
  "tipo": "tick",
  "step": 1234,
  "tiempo": 123.4,
  "V_pcc": {"1": 110.5, "2": 109.8},
  "demanda_w": 3500.0,
  "SoC_avg": 0.473,
  "SoCs": {"1": 0.50, "2": 0.0},
  "num_agentes": 2
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `V_pcc` | dict | Tensión en bornes de cada agente en volts (físicos). Clave = id agente. |
| `demanda_w` | float | Potencia de demanda total (W) a repartir entre generadores |
| `SoC_avg` | float | SoC promedio entre todos los agentes (para consenso) |
| `SoCs` | dict | SoC individual de cada agente (estado compartido) |
| `num_agentes` | int | Número de agentes en el sistema |

#### 3.1.3 Medición (Agentes → Servidor)

```json
{
  "tipo": "medicion",
  "id": 1,
  "P_ref": 3317.3,
  "SoC": 0.4479,
  "cobertura": 1,
  "SoC_avg": 0.4730,
  "paso": 35999
}
```

#### 3.1.4 Dinámica Remota (ServicioDinamica)

Capa opcional para separación de procesos (puerto TCP 6000):

```
Agente ──{"comando": "step", "dt": 0.1, "P_ref": 5000.0, "V_pcc": 110.5}──▶ Dinámica
Agente ◀───{"ok": true, "SoC": 0.48, "P_real": 4950.0, ...}────────────────── Dinámica
```

### 3.2 Ciclo de Co-simulación (por paso)

```
1. Servidor: construir tick con V_pcc (desde solver FBS)
                + SoCs + demanda
2. Servidor ──enviar_tick()──▶ Todos los agentes (broadcast TCP)
3. Cada agente:
   a. Extraer V_pcc propio del dict
   b. Ejecutar LVRT (derating si V_pcc bajo)
   c. Calcular P_ref por consenso (SoC_i - SoC_avg)
   d. modelo.step(dt, P_ref, V_pcc) → actualiza SoC, P_real
   e. enviar_medicion(P_ref, SoC, ...)
4. Servidor ◀──recibir_mediciones()── Cada agente
5. Servidor: inyecciones[nodo] = P_ag
6. Servidor: mc.registrar_inyeccion(nodo, P, Q)
7. Servidor: mc.step()
             └── ForwardBackwardSweep.resolver(inyecciones)
                 └── Backward sweep: I_nodo desde cargas
                 └── Forward sweep: V_nodo desde slack
                 └── Retorna: V[n] para todos los nodos (complejo, pu)
8. Servidor: historial.append({tiempo, V, potencias, SoC})
9. Servidor: tiempo += paso_maestro (0.1 s)
10. Repetir hasta tiempo_total (3600 s)
```

### 3.3 Flujo de Tensión Eléctrica

El solver **ForwardBackwardSweep** (`CentralPC/solver_sweep.py`) es el núcleo del cálculo eléctrico:

1. **Entrada**: Diccionario `inyecciones {nodo: (P, Q)}` en Watts y VARs
2. **Inicialización**: V[n] = 1.0 pu para todos; V[0] = V_slack (fijo)
3. **Barrido inverso (backward sweep)**:
   - Para cada nodo desde hojas hasta raíz (orden inverso por capas):
     - Calcula corriente de carga: $I_{nodo} = (S_{nodo} / V_{nodo})^*$
     - Para cada hijo: $I_{nodo} += I_{rama(hijo)}$
     - Envía corriente acumulada al padre
4. **Barrido directo (forward sweep)**:
   - Desde raíz hasta hojas (orden por capas):
     - $V_{hijo} = V_{padre} - Z_{rama} \cdot I_{rama}$
5. **Convergencia**: Si $\max(|\Delta V|) < 10^{-8}$ en todos los nodos, o hasta 1000 iteraciones
6. **Salida**: V complejo en pu para **todos los nodos** de la red

**Resultado disponible en el servidor**:
```python
mc.V  # dict {0: complex, 1: complex, ..., N: complex}
      # Cada valor es tensión compleja en pu (respecto a V_base de cada nodo)
```

Para convertir a volts físicos:
```python
V_fisico = abs(mc.V[n]) * mc.sweep.v_base_nodo[n]  # V_base_nodo[n] = 110 V
```

### 3.4 Modelo de Consenso

El balance de potencia se logra mediante un **control de consenso distribuido** basado en el SoC:

$$P_{ref,i} = \frac{P_{demanda}}{N} + K_{soc} \cdot (SoC_i - \overline{SoC})$$

- Si $SoC_i > \overline{SoC}$: el agente i aporta más potencia (se descarga más)
- Si $SoC_i < \overline{SoC}$: el agente i aporta menos (se descarga menos o carga)
- $P_{ref}$ se satura a $\pm P_{rated}$

En el caso actual (BESS + Solar):
- BESS (id=1) usa el algoritmo de consenso completo
- Solar (id=2) opera en modo *follow*: ${SoC} = P_{diponible} / P_{rated}$, no participa del consenso activamente
- El BESS compensa la diferencia: si el sol genera menos, el BESS aporta más

---

## 4. Archivos y Estructura del Proyecto

### 4.1 Núcleo de Co-simulación

| Archivo | Rol |
|---------|-----|
| `CentralPC/server_pc.py` | Servidor PC para Docker. Inicia RelojZMQ, espera N agentes, ejecuta co-simulación |
| `CentralPC/master_clock.py` | Reloj maestro que integra solver FBS y bucle temporal |
| `CentralPC/reloj_zmq.py` | Servidor TCP que coordina agentes (tick/medición) |
| `CentralPC/solver_sweep.py` | Solver FBS: flujo de potencia para redes radiales |
| `CentralPC/solver_sensitivity.py` | Solver linealizado por matrices de sensibilidad (Modo B) |
| `Mockdata/test_sim_1hora.py` | Harness de simulación: 5 nodos, 1 hora, modos local/remoto/solo-server |

### 4.2 Modelos de Generación

| Archivo | Modelo |
|---------|--------|
| `MAS/BESS_simplificado.py` | Batería simplificada (balance energético + LVRT) |
| `Solar/SolarSimplificado.py` | Solar promediado (perfil gaussiano + LVRT) |
| `BESS/SistemaBESS.py` | BESS detallado (Buck-Boost + inversor + PI Vdc) |
| `BESS/BuckBoost.py` | Convertidor Buck-Boost detallado |
| `Diesel/SistemaDiesel.py` | Generador diésel (gobernador PI + modelo mecánico) |
| `Eolica/SistemaEolico.py` | Turbina eólica (PMSG + MPPT) |
| `Hidrica/SistemaHidrico.py` | Turbina hidroeléctrica (caudal + turbina) |
| `Solar/SistemaSolar.py` | Solar detallado (panel + Boost + inversor) |
| `Demanda/SistemaDemanda.py` | Demanda con perfil temporal |

### 4.3 Agentes

| Archivo | Rol |
|---------|-----|
| `ejecutar_agente.py` | Agente BESS (local o remoto vía ServicioDinamica) |
| `ejecutar_agente_solar.py` | Agente Solar (local o remoto, con retry de conexión) |
| `MAS/agente_zmq.py` | Cliente TCP para comunicación con RelojZMQ |
| `MAS/AgenteConsenso.py` | Algoritmo de consenso distribuido |
| `MAS/cliente_dinamica.py` | Cliente TCP para ServicioDinamica |

### 4.4 Servicios de Dinámica

| Archivo | Rol |
|---------|-----|
| `Dinamica/servicio_dinamica.py` | Servidor TCP que expone modelos detallados (fábrica) |
| `Dinamica/servicio_dinamica_eolico.py` | Servidor TCP para modelo eólico |
| `Dinamica/servicio_dinamica_hidro.py` | Servidor TCP para modelo hidroeléctrico |
| `Dinamica/servicio_dinamica_diesel.py` | Servidor TCP para modelo diésel |

### 4.5 Infraestructura

| Archivo | Rol |
|---------|-----|
| `deploy_rpi_solar.py` | Despliegue automático a Raspberry Pi vía SCP |
| `requirements.txt` | Dependencias Python |
| `Docker/docker-compose.yml` | Orquestación Docker multi-contenedor |
| `RASPDIR.md` | Credenciales de acceso a RPi |

---

## 5. Escenario Experimental Estándar

El escenario base (implementado en `Mockdata/test_sim_1hora.py`) consiste en:

- **5 nodos**: Slack(0) - BESS(1) - Carga1(2) - Solar(3) - Carga2(4)
- **Duración**: 3600 segundos (1 hora) con paso de 0.1 s (36000 pasos)
- **Carga total**: 3500 W nominales (2000 + 1500 W)
- **Perfil solar**: Campana gaussiana con pico de 3 kW a los 30 minutos
- **BESS**: 5 kW, SoC inicial 50%, compensa el déficit solar vía consenso

### 5.1 Modos de Ejecución

| Modo | Descripción |
|------|-------------|
| `--local` | Todo en PC: BESS + Solar como hilos locales |
| `--remoto` | BESS en PC (hilo), Solar en RPi (ZMQ TCP) |
| `--solo-server` | Solo servidor, agentes externos conectan vía ZMQ |
| `--plot-only` | Regenerar gráficas desde CSV guardado |

### 5.2 Resultados Registrados

Cada simulación genera:
- **CSV**: `Mockdata/sim_1hora_resultados.csv` (36001 filas)
  - `tiempo`, `paso`, `P_bess`, `P_solar`, `P_carga1`, `P_carga2`
  - `SoC_bess`, `SoC_solar`
  - `V0`, `V1`, `V2`, `V3`, `V4` (tensión en pu por nodo)
- **PNG**: `Mockdata/sim_1hora_resultados.png` (gráfica 4 paneles)
  1. Tensiones nodales (todos los nodos, límites 0.95/1.05 pu)
  2. Potencia activa por nodo + balance neto
  3. SoC BESS y factor de capacidad solar
  4. Estadísticas de tensión (mínimo, promedio, máximo)

### 5.3 Rendimiento Típico

| Configuración | Pasos/s | Tiempo real (36000 pasos) |
|--------------|---------|--------------------------|
| Local (PC) | ~610 | ~59 s |
| Distribuido (BESS PC + Solar RPi) | ~622 | ~57.9 s |
| Cuello de botella | Solver FBS | ~95 % del tiempo |

---

## 6. Diagrama de Flujo de Datos

```
                 ┌──────────────────────────────────────┐
                 │         MasterClock (PC)              │
                 │                                      │
  ┌──────────────┤  ForwardBackwardSweep.resolver()     │
  │ inyecciones  │    ↓                                 │
  │ {nodo:(P,Q)} │  V = {0: complex, 1: complex, ...}   │
  │              │    ↓                                 │
  │              │  mc.V disponible para todos los nodos │
  └──────┬───────┴──────────────────────────────────────┘
         │
         │ V_pcc[nodo_agente] = abs(V[nodo]) * V_base
         │
         ▼
  ┌──────────────────┐     tick{V_pcc, demanda, SoCs}     ┌──────────────────┐
  │                  │ ──────────────────────────────────▶ │                  │
  │   RelojZMQ       │                                     │   Agente BESS    │
  │   (TCP server)   │ ◀────────────────────────────────── │   (id=1, nodo 1) │
  │   puerto 5000    │     medicion{P_ref, SoC, paso}      │                  │
  │                  │                                     │ modelo.step()    │
  │                  │     tick{V_pcc, demanda, SoCs}      │   ↓              │
  │                  │ ──────────────────────────────────▶ │ P_ref, SoC       │
  │                  │                                     └──────────────────┘
  │                  │                                     ┌──────────────────┐
  │                  │ ◀────────────────────────────────── │   Agente Solar   │
  │                  │     medicion{P_ref, SoC, paso}      │   (id=2, nodo 3) │
  └──────────────────┘                                     │   (RPi remoto)   │
         │                                                 │ modelo.step()    │
         │ mediciones {id: {P_ref, SoC, ...}}              │   ↓              │
         ▼                                                 │ P_real, SoC      │
  ┌──────────────────────────────────────────────────┐     └──────────────────┘
  │            MasterClock (cont.)                    │
  │                                                  │
  │ 1. Construir inyecciones desde mediciones         │
  │    inyecciones[nodo_BESS] = P_ref_BESS            │
  │    inyecciones[nodo_Solar] = P_ref_Solar          │
  │    inyecciones[nodo_Carga1] = (P_c1, Q_c1)        │
  │    inyecciones[nodo_Carga2] = (P_c2, Q_c2)        │
  │                                                  │
  │ 2. Registrar en MasterClock                      │
  │    mc.registrar_inyeccion(nodo, P, Q)             │
  │                                                  │
  │ 3. mc.step() → FBS solver                        │
  │    Retorna V complejo para TODOS los nodos        │
  │                                                  │
  │ 4. Log: historial + CSV + gráfica                │
  └──────────────────────────────────────────────────┘
```

---

## 7. Modelo LVRT (Low Voltage Ride Through)

Cada generador implementa LVRT en función de la tensión en su punto de conexión ($V_{pcc}$):

### BESS

```
V_pcc ≥ 0.88 pu  →  scaling = 1.0   (operación normal)
0.50 ≤ V_pcc < 0.88 pu  →  scaling = 0.88 · (V_pcc - 0.50) / (0.88 - 0.50)
V_pcc < 0.50 pu  →  scaling = 0.0   (disparo)
P_real = P_ref · scaling
```

### Solar

```
V_pcc ≥ 0.88 pu  →  P_available completo
0.50 ≤ V_pcc < 0.88 pu  →  P_available *= 0.88 · (V_pcc - 0.50) / (0.88 - 0.50)
V_pcc < 0.50 pu  →  P_available = 0.0
```

**Importante**: El LVRT actualmente no está activo porque los agentes nunca reciben $V_{pcc}$ real desde el servidor (siempre reciben `None`, cayendo al valor por defecto de 1.0 pu). Esto está identificado como mejora prioritaria.

---

## 8. Despliegue Distribuido

### 8.1 Componentes en PC (Windows, 192.168.1.6)

- Servidor ZMQ (puerto 5000)
- MasterClock + FBS Solver
- Agente BESS (hilo local)
- (Opcional) ServicioDinamica para modelos detallados

### 8.2 Componentes en RPi (192.168.1.10/11)

- Agente Solar (ejecutar_agente_solar.py)
- Modelo SolarSimplificado (embebido en el agente)

### 8.3 Conexión

- La RPi se conecta al PC vía TCP en el puerto 5000
- El agente solar implementa **retry automático** (30 intentos, 2s de espera) para tolerar que el servidor no esté listo aún
- Regla de firewall necesaria en Windows: `New-NetFirewallRule -Name "Permitir Raspberry Pi" -Direction Inbound -Protocol TCP -LocalPort 5000 -RemoteAddress "192.168.1.11" -Action Allow`
- Despliegue automatizado vía `deploy_rpi_solar.py` (SCP + SSH)

---

## 9. Limitaciones Conocidas

1. **V_pcc no propagado a agentes**: El servidor envía `{}` en lugar de las tensiones reales. LVRT deshabilitado.
2. **Ángulos no registrados**: El solver calcula ángulos complejos pero no se guardan en CSV.
3. **Cargas PQ constantes**: No hay modelo de carga dependiente de tensión (ZIP).
4. **Perfil solar sintético**: Se utiliza una campana gaussiana en lugar de datos de irradiancia real.
5. **Un solo paso de tiempo**: Todos los componentes usan 0.1 s (no hay multi-rate real).
6. **Sin reconexión automática**: Si un agente se desconecta, la simulación falla.
7. **Sin visualización en tiempo real**: Las gráficas se generan al final, no durante la ejecución.

---

## 10. Próximas Mejoras Planificadas

| Prioridad | Mejora | Archivos afectados |
|-----------|--------|-------------------|
| P1 | Propagar V_pcc real a agentes (habilitar LVRT) | `test_sim_1hora.py`, `ejecutar_agente.py`, `ejecutar_agente_solar.py` |
| P2 | Registrar V_pcc físico en CSV con etiquetas explícitas | `test_sim_1hora.py` |
| P3 | Gráficas de tensión en bornes de generadores | `test_sim_1hora.py` (`_graficar`) |
| P4 | Perfiles de irradiancia real desde CSV externo | `SolarSimplificado.py` |
| P5 | Visualización WebSocket en tiempo real | Nuevo: `GUI/` |
| P6 | Cargas ZIP dependientes de tensión | `Demanda/` |
| P7 | Multi-rate (0.5 s / 1 ms) en BESS | `BESS_simplificado.py` |
