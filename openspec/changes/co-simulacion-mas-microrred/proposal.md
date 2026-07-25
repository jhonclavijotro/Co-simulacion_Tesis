# Sistema Multi-Agente para Control Primario y Secundario de Microrred Distribuida

## Summary
Desarrollo completo de un Sistema Multi-Agente (MAS) para el control primario y secundario de tensión y potencia reactiva en una microrred de baja tensión conectada a la red principal, utilizando consenso líder-seguidor de tiempo finito. El proyecto implementa 6 fuentes de generación (Solar, Eólico, Diesel, Hidrocinético, BESS, Demanda) con modelos físicos en Python puro, dos modos de flujo de potencia (Forward-Backward Sweep y Matrices de Sensibilidad), comunicación ZeroMQ con stdlib socket, contenerización Docker con separación estricta de procesos (dinámica + agente por nodo), GUI Flask + Chart.js, persistencia InfluxDB y publicación MQTT. Despliegue verificado en Raspberry Pi con 7 contenedores co-simulando 600 pasos.

## Motivation
Las microrredes de baja tensión requieren esquemas de control distribuido que no dependan de un único punto de fallo. Los enfoques centralizados tradicionales (SCADA, DMS) presentan limitaciones de escalabilidad, latencia y vulnerabilidad. Este proyecto propone un MAS con consenso de tiempo finito donde cada nodo de generación ejecuta un agente inteligente que se comunica con sus vecinos para compartir información de estado (SoC, tensión, potencia) y alcanzar acuerdos distribuidos sobre la inyección de potencia reactiva para regulación de tensión, sin necesidad de un coordinador central.

**Base teórica**:
- Christakou et al. (2013) — Coeficientes de sensibilidad para control de tensión en redes radiales desbalanceadas
- Chang et al. (2007) — Algoritmo mejorado de barrido para flujo de carga en sistemas radiales
- Consenso distribuido de tiempo finito para sistemas multi-agente lineales

## Proposed Solution

### Arquitectura General
Cada nodo de generación ejecuta **dos contenedores Docker independientes** comunicados via ZeroMQ (TCP/JSON con stdlib socket+select):

```
Nodo Generación i
├── Contenedor A: Dinámica Física (modelo eléctrico/mecánico)
└── Contenedor B: Agente Consenso MAS (control distribuido)
        │
        └── ZeroMQ ──→ PC Central (Reloj Maestro + Flujo de Potencia)
                            │
                            ├── InfluxDB (históricos cada 500 ms)
                            ├── Mosquitto MQTT (clima meteorológico)
                            └── GUI Flask + Chart.js (dashboard)
```

### Componentes Implementados

**1. Modelos Físicos (7 fuentes):**
- **Solar**: Panel fotovoltaico diodo único + Newton-Raphson, MPPT P&O, Boost Converter, Inversor grid-following con PLL
- **Eólico**: Aerogenerador con curva Cp(λ), PMSG con integración Euler, Rectificador, Inversor
- **Diesel**: Motor Diesel con control PI, modelo espacio-estado, inversor
- **Hidrocinético**: Derivado del eólico (ρ_agua = 1000 kg/m³)
- **BESS**: Batería Li-ion (Shepherd simplificado), Buck-Boost bidireccional, modos promedio y detallado (EMT)
- **Demanda**: Perfiles P, Q desde CSV con interpolación lineal

**2. PC Central (2 modos de flujo de potencia):**
- **Modo A — Forward-Backward Sweep**: Algoritmo de barrido para redes radiales
- **Modo B — Matrices de Sensibilidad**: Perturbación alrededor del caso base
- **Reloj Maestro**: Coordinación temporal de todos los agentes vía ZeroMQ

**3. Sistema Multi-Agente:**
- **AgenteConsenso**: Difusión de tablas SoC entre vecinos con timestamps
- **AgenteBESS**: P_ref proporcional a desviación de SoC del promedio global
- **Comunicación ZeroMQ**: Protocolo TCP/JSON con stdlib socket+select (sin pyzmq)

**4. Contenerización Docker:**
- 3 Dockerfiles (dinamica, agente, gui)
- 2 docker-compose (core 7 servicios, completo 15 servicios)

**5. GUI y Monitoreo:**
- Flask + Bootstrap 5 + Chart.js
- InfluxDB 2.x vía HTTP API
- Mosquitto MQTT para clima

**6. Calidad:**
- Type hints en funciones públicas
- 24 tests unitarios (23 pasan)
- np.pi, decoupledC corregido

## Impact
- **Breaking changes**: Ninguno
- **Dependencias**: numpy>=1.24, scipy>=1.10, matplotlib>=3.7, flask, gunicorn, paho-mqtt
- **Repositorio**: ~3000 líneas Python en 15 paquetes
- **Documentación**: 12 papers, Constitucion.md, Tasks.md, Consultas.md, FUTURO.md

## Cronología Real del Proyecto
| FASE | Descripción | Estado |
|------|-------------|--------|
| FASE 0 | Arquitectura y Gestión | Completado |
| FASE 1 | Refactor de Código Base | Completado |
| FASE 1.5 | Nuevos Modelos (Hidrocinético) | Completado |
| FASE 2 | DRY (unificación common/) | Completado |
| FASE 3 | Componentes MAS | Completado |
| FASE 4 | Contenerización y Despliegue | Completado |
| FASE 5 | GUI, Monitoreo y Persistencia | Completado |
| FASE 6 | Mejoras de Calidad | Completado |
