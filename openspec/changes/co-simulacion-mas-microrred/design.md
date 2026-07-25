# Design: Sistema Multi-Agente para Microrred Distribuida

## Arquitectura General

```
                    ┌──────────────────────────────────────┐
                    │           PC Central                  │
                    │  ┌──────────┐  ┌──────────────────┐  │
                    │  │ Reloj    │  │ Flujo de Potencia │  │
                    │  │ Maestro  │  │ Sweep / Sensib.  │  │
                    │  │ (ZeroMQ) │  │ (Modo A / B)     │  │
                    │  └────┬─────┘  └──────────────────┘  │
                    └───────┼──────────────────────────────┘
                            │ ZeroMQ (PUB/PULL + SUB/PUSH)
          ┌─────────────────┼────────────────────┐
          │                 │                    │
   ┌──────▼──────┐  ┌──────▼──────┐   ┌────────▼────────┐
   │ Dinamica 1  │  │ Dinamica 2  │   │   Dinamica 3    │
   │ (BESS SoC0.8)│  │ (BESS SoC0.5)│  │ (BESS SoC0.3)   │
   │ TCP:6000    │  │ TCP:6000    │   │  TCP:6000        │
   └──────┬──────┘  └──────┬──────┘   └────────┬────────┘
          │ TCP/JSON       │ TCP/JSON          │ TCP/JSON
   ┌──────▼──────┐  ┌──────▼──────┐   ┌────────▼────────┐
   │ Agente 1    │  │ Agente 2    │   │   Agente 3      │
   │ Consenso    │◄─┤ Consenso    │◄──┤   Consenso      │
   │ Vecinos:2,3 │  │ Vecinos:1,3 │   │   Vecinos:1,2   │
   └─────────────┘  └─────────────┘   └─────────────────┘
```

## Stack Tecnológico

| Capa | Tecnología | Versión |
|------|-----------|---------|
| Lenguaje | Python | 3.11+ |
| Cálculo | numpy, scipy | 1.24+, 1.10+ |
| Visualización | matplotlib | 3.7+ |
| Contenerización | Docker + Compose | 20.10+ / v2 |
| Broker MQTT | Mosquitto (Eclipse) | 2.x |
| Time Series DB | InfluxDB | 2.7 |
| GUI | Flask + Gunicorn + Chart.js | Flask 3.x |
| Comunicación | ZeroMQ (stdlib socket+select) | — |
| Proxy SSH | PuTTY (plink, pscp) | 0.83 |
| Testing | pytest | 7.x |

## Modelos Físicos

### Solar
- Panel: Modelo diodo único (5 parámetros: Iph, Io, n, Rs, Rsh)
- Solver: Newton-Raphson para V(I) o I(V)
- MPPT: Perturb & Observe (P&O) con step_size=0.5
- Convertidor: Boost DC-DC promediado (L, C, D, f_sw)
- Red: Inversor grid-following con PLL+Park+PI

### Eólico
- Turbina: Cp(λ) con λ_opt=8.1, Cp_max=0.48
- Generador: PMSG con modelo espacio-estado (Euler)
- Rectificador: Modelo promediado con PI
- Red: Inversor grid-following

### BESS
- Batería: Modelo Shepherd simplificado (V_oc(SoC), R_int)
- Convertidor: Buck-Boost bidireccional promediado
- Modos: "promedio" (f_sw) y "detallado" (EMT con IGBT)
- Control: PI en cascada (I→V→P)

### Demanda
- Perfiles: Carga desde CSV (t, P, Q)
- Interpolación: Lineal entre puntos
- Interface: step() → tuple(P, Q)

## Protocolo Comunicación ZeroMQ

```
RelojZMQ (PUB): "tick <step>" a todos los agentes
Cada AgenteZMQ (SUB): recibe tick, procesa, responde
RelojZMQ (PULL): recibe resultados de todos los agentes
CoordinadorZMQ: sincroniza, ejecuta sweep, publica setpoints

Formato JSON:
{
  "tipo": "tick|medicion|setpoint|resultado",
  "origen": "pc_central|agente_N",
  "timestamp": 1234.567,
  "datos": { "V": 110.0, "P": 5000.0, "Q": 0.0 }
}
```

## Flujo de Co-simulación (600 pasos verificado)

1. PC Central inicia servidor ZeroMQ
2. Cada dinámica inicia servidor TCP
3. Cada agente se conecta a PC Central + su dinámica
4. Bucle (600 iteraciones):
   a. PC Central publica "tick N"
   b. Agentes reciben tick, solicitan V desde dinámica
   c. Agentes ejecutan consenso: difunden tablas SoC
   d. Agentes computan P_ref desde desviación SoC
   e. PC Central recibe todas las mediciones
   f. PC Central ejecuta flujo de potencia (sweep/sensibilidad)
   g. PC Central publica nuevos setpoints V_ref
   h. Agentes aplican setpoint a su dinámica
5. Fin simulación

## Estructura del Repositorio

```
Co-simulacion - opencode/
├── Constitucion.md       # Constitución del proyecto
├── Tasks.md              # Kanban original (58 tareas)
├── Consultas.md          # Registro literatura (D001-D019)
├── PLAN.md               # Master prompt V4
├── FUTURO.md             # Plan de expansión futura
├── RASPDIR.md            # Credenciales RPi
├── Makefile              # Automatización
├── requirements.txt      # Dependencias
├── deploy.py             # Despliegue SCP/SSH
├── ejecutar_agente.py    # Entry point agente
├── debug_mas.py          # Debug 3 agentes
├── docker-compose.yml    # Orquestación core
├── docker-compose.full.yml  # Stack completo
│
├── common/               # Módulos compartidos
│   ├── Transformadas.py  # Clarke/Park/PLL
│   ├── RedTrifasica.py   # Modelo red trifásica
│   ├── GridInverter.py   # Inversor grid-following
│   ├── Rectificador.py   # Rectificador PWM
│   └── PMSG.py           # Generador síncrono imán permanente
│
├── Solar/                # Modelo solar fotovoltaico
├── Eolica/               # Modelo eólico
├── Diesel/               # Modelo diesel
├── Hidrica/              # Modelo hidrocinético
├── BESS/                 # Modelo batería + buck-boost
├── Demanda/              # Perfiles de carga
│
├── MAS/                  # Sistema Multi-Agente
│   ├── AgenteConsenso.py     # Consenso difusivo
│   ├── AgenteBESS.py         # Agente BESS
│   ├── BESS_simplificado.py  # Batería simplificada
│   ├── CoordinadorMAS.py     # Orquestador local
│   ├── agente_zmq.py         # Cliente ZeroMQ
│   ├── coordinador_zmq.py    # Coordinador ZeroMQ
│   └── cliente_dinamica.py   # Cliente dinámica remota
│
├── CentralPC/            # PC Central
│   ├── master_clock.py       # Reloj maestro
│   ├── server_pc.py          # Entry point Docker
│   ├── solver_sweep.py       # FBS (Modo A)
│   ├── solver_sensitivity.py # Sensibilidad (Modo B)
│   ├── reloj_zmq.py          # Servidor ZeroMQ
│   ├── logger_influx.py      # Logger InfluxDB
│   ├── climate_publisher.py  # MQTT clima
│   └── generador_topologia.py# Generador topológico
│
├── Dinamica/             # Servicio dinámica remota
│   └── servicio_dinamica.py
│
├── GUI/                  # Interfaz gráfica
│   ├── app.py                # Flask app
│   ├── data/                 # Perfiles ejemplo CSV
│   └── templates/index.html  # Dashboard Chart.js
│
├── Docker/               # Archivos Docker
│   ├── Dockerfile.dinamica
│   ├── Dockerfile.agente
│   └── Dockerfile.gui
│
├── Docs/                 # Documentación academia
│   └── *.pdf (12 papers de referencia)
│
├── tests/                # Tests unitarios
│   └── test_mas.py          # 24 tests
│
└── openspec/             # OpenSpec spec-driven development
    ├── config.yaml
    ├── specs/
    └── changes/
        └── co-simulacion-mas-microrred/
            ├── proposal.md
            ├── design.md
            └── tasks.md
```
