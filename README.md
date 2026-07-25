# Sistema Multi-Agente para Microrred Distribuida

![Status](https://img.shields.io/badge/status-development-yellow.svg)
![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

---
⚠️ **Disclaimer**: Este proyecto se encuentra actualmente en fase de desarrollo activo. La arquitectura y las funcionalidades están sujetas a cambios conforme avance la implementación y las pruebas de validación.
---

Este repositorio contiene la implementación de un **Sistema Multi-Agente (MAS)** avanzado para el control primario y secundario de tensión y potencia reactiva en microrredes de baja tensión.

El proyecto permite la co-simulación distribuida de fuentes de energía renovable, almacenamiento y demanda, operando bajo un esquema de consenso líder-seguidor de tiempo finito, sin necesidad de librerías comerciales de flujo de potencia.

## Arquitectura del Sistema

El sistema utiliza un enfoque de separación de procesos donde cada nodo de generación física tiene su propio agente de control inteligente.

```text
+-------------------------------------------------------------+
| PC Central (Master Clock + Load Flow Solver: FBS/Sensitivity)|
+------------------------------+------------------------------+
                               | ZeroMQ (TCP/JSON)
  ┌────────────────────────────┴───────────────────────────┐
  │                        MAS Network                     │
┌─┴────────────┐    ┌──────────────┐    ┌──────────────────┐
│ Nodo Gen 1   │    │ Nodo Gen 2   │    │ Nodo Gen 3       │
│ [Dynamics]   │    │ [Dynamics]   │    │ [Dynamics]       │
│ [MAS Agent]  │    │ [MAS Agent]  │    │ [MAS Agent]      │
└──────┬───────┘    └──────┬───────┘    └─────────┬────────┘
       └───────────────────┴──────────────────────┘
                   │
         ┌─────────┴─────────┐
         │ GUI + Monitor     │
         │ (Flask/Influx/MQTT)│
         └───────────────────┘
```

## Características Principales

*   **MAS Distribuido**: Algoritmos de consenso de tiempo finito para reparto de potencia reactiva basado en SoC.
*   **Modelos Físicos (Python Puro)**: Solar, Eólico, Diesel, Hidrocinético, BESS y Demanda modelados sin dependencias propietarias.
*   **Orquestación**: Contenedores Docker con separación estricta (dinámica + agente por nodo).
*   **Monitoreo**: Dashboard en tiempo real (Flask) con persistencia histórica (InfluxDB) y telemetría (MQTT).
*   **Spec-Driven Development**: Integración con *OpenSpec* para trazabilidad.

## Stack Tecnológico

| Capa | Tecnología |
|------|-----------|
| **Core** | Python 3.11+, numpy, scipy |
| **Infraestructura** | Docker, Docker Compose |
| **Persistencia** | InfluxDB 2.x |
| **Monitoreo** | Mosquitto MQTT |
| **Frontend** | Flask, Chart.js, Bootstrap 5 |
| **Comunicación** | ZeroMQ (stdlib) |

## Ejecución

### Local
1. `docker-compose -f docker-compose.full.yml up`
2. Acceder a `http://localhost:5000`

### Raspberry Pi
Despliegue mediante `deploy.py` utilizando variables de entorno para credenciales:
```bash
export RPI_USER="..." RPI_HOST="..." RPI_PASSWORD="..."
python deploy.py
```

## Licencia
Uso académico y de investigación. Prohibida su redistribución comercial sin autorización.
