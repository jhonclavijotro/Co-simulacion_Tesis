<div align="center">

# ⚡ MAS-Microgrid

### Sistema Multi-Agente Distribuido para el Control Secundario en Tiempo Finito de una Microrred Inteligente Co-simulada

![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Containerized-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![ZeroMQ](https://img.shields.io/badge/ZeroMQ-Messaging-DF0000?style=for-the-badge&logo=zeromq&logoColor=white)
![InfluxDB](https://img.shields.io/badge/InfluxDB-Telemetry-22ADF6?style=for-the-badge&logo=influxdb&logoColor=white)
![MQTT](https://img.shields.io/badge/MQTT-Pub/Sub-660066?style=for-the-badge&logo=eclipsemosquitto&logoColor=white)
![LaTeX](https://img.shields.io/badge/LaTeX-Thesis-008080?style=for-the-badge&logo=latex&logoColor=white)
![Raspberry Pi](https://img.shields.io/badge/Raspberry_Pi_5-Cluster-A22846?style=for-the-badge&logo=raspberrypi&logoColor=white)

[![Tests](https://img.shields.io/badge/tests-24%2F24_passed-brightgreen?style=flat-square&logo=pytest&logoColor=white)](#testing)
[![License](https://img.shields.io/badge/license-Academic-blue?style=flat-square)](#license)
[![Status](https://img.shields.io/badge/status-Active_Development-yellow?style=flat-square)](#project-status)

---

**Tesis de Grado** · Jhonathan Clavijo

[Arquitectura](#-arquitectura) · [Instalación](#-instalación) · [Uso](#-uso-rápido) · [Tests](#-testing) · [Documentación](#-documentación)

</div>

---

## 📋 Resumen

Este repositorio contiene la implementación completa de un **Sistema Multi-Agente (MAS)** distribuido para el **control secundario de tensión y reparto equitativo de potencia reactiva** en una microrred inteligente co-simulada, desplegada en un clúster de hardware distribuido (Raspberry Pi 5).

El sistema utiliza un protocolo de **consenso líder-seguidor en tiempo finito** que garantiza convergencia determinista, superando las limitaciones de los esquemas asintóticos convencionales. La co-simulación se ejecuta mediante dos solucionadores eléctricos propios desarrollados desde cero (sin dependencias de librerías tipo Pandapower).

### Características Principales

- 🧠 **Consenso en Tiempo Finito** — Ley de control no lineal `sig(e)^α + sig(e)^β` con convergencia determinista < 2s
- 🔌 **Dos Solucionadores Propios** — Forward-Backward Sweep (Modo A) y Matrices de Sensibilidad S<sub>VQ</sub> (Modo B)
- 🐳 **Arquitectura Docker Desacoplada** — Contenedores separados para dinámica física y agente de consenso por nodo
- 📡 **Sincronización ZeroMQ** — Reloj maestro REP/PUB con paso de 500 ms
- 📊 **Telemetría en Tiempo Real** — InfluxDB + MQTT para series meteorológicas y datos de operación
- 🖥️ **Centro de Mando GUI** — Dashboard web y aplicación de escritorio Tkinter con despliegue en 1-clic
- 🍓 **Hardware Distribuido** — Validación experimental en clúster de Raspberry Pi 5

---

## 🏗 Arquitectura

```
┌─────────────────────────────────────────────────────────────────────┐
│                         PC CENTRAL                                  │
│                                                                     │
│   ┌──────────────────────┐   ┌──────────────────────┐               │
│   │   Centro de Mando    │   │   Reloj Maestro ZMQ  │               │
│   │   (GUI / Dashboard)  │──▶│   master_clock_zmq   │               │
│   │   InfluxDB + MQTT    │   │   PUB / REP @ 500ms  │               │
│   └──────────────────────┘   └─────────┬────────────┘               │
│                                        │                            │
│              ┌─────────────────────────┼──────────────────────┐     │
│              │                         │                      │     │
│   ┌──────────▼──────────┐   ┌──────────▼──────────┐          │     │
│   │  Modo A: FBS        │   │  Modo B: Sensibilid.│          │     │
│   │  Forward-Backward   │   │  S_VQ = ∂V/∂Q       │          │     │
│   │  Sweep Iterativo    │   │  Schur Complement    │          │     │
│   └─────────────────────┘   └─────────────────────┘          │     │
└──────────────────────────────────────────────────────────────┘     │
                                                                     │
                    ZeroMQ (tcp://*)                                  │
           ┌──────────────┬──────────────┬──────────────┐            │
           ▼              ▼              ▼              ▼            │
┌─────────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│   NODO 1        │ │   NODO 2     │ │   NODO 3     │ │   NODO 4     │
│   Raspberry Pi  │ │   Rasp. Pi   │ │   Rasp. Pi   │ │   Rasp. Pi   │
│                 │ │              │ │              │ │              │
│ ┌─────────────┐ │ │ ┌──────────┐ │ │ ┌──────────┐ │ │ ┌──────────┐ │
│ │  Container  │ │ │ │Container │ │ │ │Container │ │ │ │Container │ │
│ │  Dinámica   │ │ │ │Dinámica  │ │ │ │Dinámica  │ │ │ │Dinámica  │ │
│ │  Diésel     │ │ │ │Solar PV  │ │ │ │Eólica    │ │ │ │Hídrica   │ │
│ └─────────────┘ │ │ └──────────┘ │ │ └──────────┘ │ │ └──────────┘ │
│ ┌─────────────┐ │ │ ┌──────────┐ │ │ ┌──────────┐ │ │ ┌──────────┐ │
│ │  Container  │ │ │ │Container │ │ │ │Container │ │ │ │Container │ │
│ │  Agente     │ │ │ │Agente    │ │ │ │Agente    │ │ │ │Agente    │ │
│ │  Consenso   │ │ │ │Consenso  │ │ │ │Consenso  │ │ │ │Consenso  │ │
│ │  (Líder)    │ │ │ │(Seguidor)│ │ │ │(Seguidor)│ │ │ │(Seguidor)│ │
│ └─────────────┘ │ │ └──────────┘ │ │ └──────────┘ │ │ └──────────┘ │
└─────────────────┘ └──────────────┘ └──────────────┘ └──────────────┘
```

### Modos de Operación

| Modo | Descripción | Nodo Líder |
|------|-------------|------------|
| **ONLINE** | Microrred conectada a la red principal (nodo Slack externo) | Nodo Slack |
| **OFFLINE** | Modo isla autónoma (desconectada de la red principal) | Nodo 1 — Diésel (regulación V/f) |

---

## 📁 Estructura del Proyecto

```
Tesis_Grado/
├── Agents/                          # Agentes de consenso distribuido
│   ├── finite_time_consensus.py     #   Protocolo líder-seguidor en tiempo finito
│   └── node_dynamic_process.py      #   Proceso dinámico por nodo (integrador)
│
├── Central_PC/                      # Motor de co-simulación (PC Central)
│   ├── master_clock_zmq.py          #   Reloj maestro ZMQ (PUB/REP @ 500ms)
│   ├── power_flow_fbs.py            #   Modo A — Forward-Backward Sweep
│   └── sensitivity_matrices.py      #   Modo B — Matrices de Sensibilidad S_VQ
│
├── Solar/                           # Modelo dinámico: Sistema Solar Fotovoltaico
├── Eolica/                          # Modelo dinámico: Sistema Eólico PMSG
├── Hidrica/                         # Modelo dinámico: Sistema Hidrocinético
├── Diesel/                          # Modelo dinámico: Generador Diésel + Gobernador
├── BESS/                            # Modelo dinámico: Almacenamiento en Baterías (SoC, LVRT)
├── Demanda/                         # Modelo de carga/demanda variable
├── common/                          # Módulos compartidos (graficación, utilidades)
│
├── Docker/                          # Infraestructura de contenedores
│   ├── Dockerfile.dynamic           #   Imagen para dinámica físico-eléctrica
│   ├── Dockerfile.agent             #   Imagen para agente de consenso
│   └── docker_compose_generator.py  #   Generador paramétrico de manifiestos YAML
│
├── GUI/                             # Centro de Mando y telemetría
│   ├── gui_command_center.py        #   Orquestador principal de la co-simulación
│   ├── app_gui_tkinter.py           #   Aplicación de escritorio (Tkinter)
│   ├── web_dashboard.html           #   Dashboard web interactivo
│   ├── server_dashboard.py          #   Servidor web para dashboard
│   ├── mqtt_publisher.py            #   Publicador MQTT de series meteorológicas
│   └── influx_telemetry.py          #   Logger de telemetría a InfluxDB
│
├── Scripts/                         # Scripts de despliegue
│   └── deploy_raspberry.py          #   Instalador automatizado para clúster RPi 5
│
├── config/                          # Topologías de red eléctrica
│   ├── topologia_BT_4nodos.csv      #   Red BT radial — 4 nodos
│   ├── topologia_BT_mallada_4nodos.csv  #   Red BT mallada — 4 nodos
│   └── topologia_MT_Nnodos.csv      #   Red MT parametrizable — N nodos
│
├── mock_data/                       # Generador de datos sintéticos (irradiancia, viento, caudal)
├── tests/                           # Suite de pruebas unitarias y E2E (24 tests)
├── tools/                           # Herramientas auxiliares (LaTeX MCP, Obsidian builder, arXiv search)
│
├── Thesis_LaTeX/                    # Documento de tesis (LaTeX)
│   ├── main.tex                     #   Documento principal
│   ├── chapters/                    #   Capítulos 1–6
│   ├── figures/                     #   Figuras e imágenes
│   └── references.bib               #   Bibliografía (≥ 2022)
│
├── obsidian_vault/                  # Base de conocimiento Zettelkasten (Obsidian)
│
├── Makefile                         # Automatización de comandos
├── requirements.txt                 # Dependencias Python
├── Constitucion.md                  # Alcance, estándares y delimitaciones
├── PLAN.md                          # Plan maestro del proyecto
└── Tasks.md                         # Tablero Kanban de seguimiento
```

---

## 🚀 Instalación

### Requisitos Previos

- **Python** 3.12+
- **Docker** y **Docker Compose** (para despliegue en contenedores)
- **InfluxDB** 2.x (opcional — el sistema incluye fallback local)
- **Mosquitto MQTT Broker** (opcional — incluye fallback sin broker)

### Configuración del Entorno

```bash
# 1. Clonar el repositorio
git clone https://github.com/<usuario>/MAS-Microgrid.git
cd MAS-Microgrid

# 2. Crear y activar entorno virtual
python -m venv .venv

# Windows
.\.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Verificar la instalación
make test
```

### Despliegue en Clúster Raspberry Pi 5

```bash
# Generar manifiestos Docker automáticamente
python Docker/docker_compose_generator.py

# Desplegar en el clúster RPi
python Scripts/deploy_raspberry.py --host 192.168.1.10 --user jhonclavijotro
```

---

## ⚡ Uso Rápido

### Ejecutar el Reloj Maestro (PC Central)

```bash
# Modo A — Forward-Backward Sweep (redes radiales)
make run-master-fbs

# Modo B — Matrices de Sensibilidad (redes malladas)
make run-master-sens
```

### Lanzar el Centro de Mando

```bash
# Dashboard Web (http://localhost:8080/web_dashboard.html)
make run-gui-web

# Aplicación de Escritorio (Tkinter)
make run-gui-desktop
```

### Ejecutar un Nodo Dinámico Standalone

```python
from Agents.node_dynamic_process import NodeDynamicProcess

proc = NodeDynamicProcess(node_id=2, source_type="SOLAR")
result = proc.step(V_pcc=400.0, Q_ref=1000.0)
print(result)
# {'node_id': 2, 'source_type': 'SOLAR', 'step': 1, 'P_w': 8432.15, 'Q_var': 987.32}
```

### Ejecutar un Paso de Consenso

```python
from Agents.finite_time_consensus import FiniteTimeConsensusAgent

agent = FiniteTimeConsensusAgent(agent_id=2, Q_max=30000.0, mode="ONLINE")
agent.set_adjacency({1: 1, 3: 1})

neighbors = {1: {"V": 1.00, "Q_ratio": 0.20}, 3: {"V": 0.98, "Q_ratio": 0.40}}
dV, dQ = agent.update_consensus(V_i=0.99, Q_i=9000.0, neighbor_states=neighbors, dt=0.5)
print(f"delta_V = {dV:.6f} p.u., delta_Q = {dQ:.2f} VAR")
```

---

## 🧪 Testing

La suite de pruebas del proyecto cubre los módulos críticos del sistema:

```bash
# Ejecutar toda la suite
python -m pytest tests/ -v

# Ejecutar un módulo específico
python -m pytest tests/test_power_flow.py -v
python -m pytest tests/test_finite_time_consensus.py -v
```

### Cobertura de Tests

| Módulo de Test | Tests | Descripción |
|---|---|---|
| `test_power_flow.py` | 2 | Solucionadores FBS y Sensibilidad |
| `test_finite_time_consensus.py` | 2 | Consenso ONLINE y OFFLINE (líder) |
| `test_docker_generator.py` | 1 | Generación de manifiestos Docker |
| `test_sensitivity_mesh.py` | 3 | Redes malladas: RADIAL, RING_ZBUS, GUI switching |
| `test_inverter_aggregation.py` | 4 | Agregación de inversores en paralelo (Solar, BESS) |
| `test_zmq_master.py` | 2 | Reloj maestro ZMQ (FBS + Sensibilidad) |
| `test_gui_and_telemetry.py` | 3 | MQTT, InfluxDB y flujo GUI completo |
| `test_end_to_end_hil.py` | 2 | E2E: Despliegue RPi + Co-simulación |
| `test_latex_mcp_server.py` | 5 | Scaffolding, parsing, compilación LaTeX |
| **Total** | **24** | **24/24 passed ✅** |

---

## 🔬 Modelos Físicos de Recursos Distribuidos

| Recurso | Modelo | Archivo |
|---|---|---|
| ☀️ **Solar PV** | Array PV + Boost MPPT + Inversor VSI dq | `Solar/SistemaSolar.py` |
| 💨 **Eólico** | Turbina PMSG + Rectificador + Boost + VSI | `Eolica/SistemaEolico.py` |
| 🌊 **Hidrocinético** | Turbina hidráulica + PMSG + Convertidor | `Hidrica/SistemaHidrico.py` |
| ⛽ **Diésel** | Motor + Gobernador de velocidad + Generador síncrono | `Diesel/SistemaDiesel.py` |
| 🔋 **BESS** | Batería Li-ion (SoC) + Bidireccional DC-DC + VSI (LVRT) | `BESS/SistemaBESS.py` |
| 🏠 **Demanda** | Perfil de carga ZIP variable | `Demanda/SistemaDemanda.py` |

Todos los modelos utilizan integración de paso fino (1 ms) con submuestreo al paso global de co-simulación (500 ms).

---

## 🔧 Stack Tecnológico

| Componente | Tecnología |
|---|---|
| **Lenguaje** | Python 3.12+ |
| **Cómputo numérico** | NumPy, SciPy |
| **Contenedores** | Docker, Docker Compose |
| **Mensajería en tiempo real** | ZeroMQ (pyzmq) — REP/PUB |
| **Publicación de datos** | MQTT (paho-mqtt) |
| **Telemetría y almacenamiento** | InfluxDB (influxdb-client) |
| **Visualización** | Matplotlib, Web Dashboard (HTML/JS) |
| **GUI de escritorio** | Tkinter |
| **Documentación académica** | LaTeX (latexmk) |
| **Base de conocimiento** | Obsidian (Zettelkasten) |
| **Testing** | pytest, pytest-mock |
| **Hardware target** | Raspberry Pi 5 (clúster distribuido) |

---

## 📖 Documentación

| Documento | Descripción |
|---|---|
| [`PLAN.md`](PLAN.md) | Plan maestro del proyecto |
| [`Constitucion.md`](Constitucion.md) | Alcance, estándares de código y bibliografía |
| [`Tasks.md`](Tasks.md) | Tablero Kanban de seguimiento |
| [`Thesis_LaTeX/`](Thesis_LaTeX/) | Documento completo de la tesis (6 capítulos) |
| [`obsidian_vault/`](obsidian_vault/) | Base de conocimiento Zettelkasten con notas enlazadas |

---

## 🗺️ Roadmap

- [x] Motor de co-simulación con solucionadores FBS y Sensibilidad
- [x] Protocolo de consenso líder-seguidor en tiempo finito
- [x] Arquitectura Docker desacoplada (dinámica + agente)
- [x] Centro de Mando GUI con MQTT e InfluxDB
- [x] Suite de 24 pruebas unitarias y E2E
- [ ] Validación experimental completa en clúster RPi 5
- [ ] Redacción final de capítulos de la tesis
- [ ] Análisis de ciberseguridad en MAS (FDI/DoS)
- [ ] Control terciario de despacho económico distribuido

---

## 📄 Licencia

Este proyecto es parte de una **tesis de grado académica**. Todos los derechos reservados.
El código y la documentación están disponibles para fines académicos y de investigación.

---

## 👤 Autor

**Jhonathan Clavijo**

---

<div align="center">

*Desarrollado como Tesis de Grado*

**Sistema Multi-Agente Distribuido para el Control Secundario en Tiempo Finito de una Microrred Inteligente Co-simulada**

</div>
