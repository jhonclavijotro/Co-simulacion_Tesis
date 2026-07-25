# Sistema Multi-Agente para Microrred Distribuida

Este repositorio contiene la implementación de un **Sistema Multi-Agente (MAS)** avanzado para el control primario y secundario de tensión y potencia reactiva en microrredes de baja tensión.

El proyecto permite la co-simulación distribuida de fuentes de energía renovable, almacenamiento y demanda, operando bajo un esquema de consenso líder-seguidor de tiempo finito, sin necesidad de librerías comerciales de flujo de potencia.

## Arquitectura del Sistema

El sistema utiliza un enfoque de **separación de procesos**:

1.  **Nodos de Generación**: Cada nodo (Solar, Eólico, Diesel, Hidrocinético, BESS) se divide en dos contenedores Docker independientes:
    *   **Contenedor de Dinámica**: Modelado físico del componente.
    *   **Contenedor de Agente**: Control distribuido (MAS) basado en consenso.
    *   *Comunicación*: ZeroMQ (TCP/JSON).
2.  **PC Central**: Actúa como reloj maestro y solver de red (Forward-Backward Sweep o Matrices de Sensibilidad).
3.  **GUI y Monitoreo**: Dashboard Flask + Chart.js con almacenamiento en InfluxDB y publicación de variables climáticas vía MQTT.

## Características Principales

*   **Modelos Físicos en Python Puro**: Modelado detallado de fuentes de energía y sistemas de almacenamiento (BESS) sin dependencias de librerías propietarias.
*   **MAS Distribuido**: Algoritmos de consenso de tiempo finito para reparto de potencia reactiva basado en SoC (State of Charge).
*   **Orquestación**: Despliegue listo para producción en Raspberry Pi mediante Docker Compose.
*   **Visualización**: Interfaz web en tiempo real para monitoreo de estados, subida de perfiles y despliegue automático.
*   **Desarrollo Spec-Driven**: Configurado con *OpenSpec* para trazabilidad de requisitos, diseño y tareas.

## Stack Tecnológico

*   **Lenguaje**: Python 3.11+
*   **Cálculo Numérico**: `numpy`, `scipy`
*   **Infraestructura**: Docker, Docker Compose
*   **Monitoreo**: InfluxDB 2.x, Mosquitto MQTT
*   **Web**: Flask, Chart.js, Bootstrap 5
*   **Comunicación**: ZeroMQ (protocolo TCP/JSON vía stdlib)

## Instalación y Ejecución

### Requisitos previos
*   Python 3.11+
*   Docker y Docker Compose
*   *Para Raspberry Pi*: SSH configurado

### Ejecución Local
1.  Clonar el repositorio: `git clone git@github.com:jhonclavijotro/Co-simulacion_Tesis.git`
2.  Instalar dependencias: `pip install -r requirements.txt`
3.  Lanzar stack completo: `docker-compose -f docker-compose.full.yml up`
4.  Acceder a la GUI en `http://localhost:5000`

### Despliegue en RPi
Utilice el script `deploy.py` configurando las variables de entorno necesarias:
```bash
export RPI_USER="tu_usuario"
export RPI_HOST="192.168.1.10"
export RPI_PASSWORD="tu_password"
python deploy.py
```

## Estructura del Proyecto

*   `/MAS`: Lógica de agentes, consenso y orquestación ZeroMQ.
*   `/CentralPC`: Solver de flujo de potencia y reloj maestro.
*   `/Dinamica`: Servicios de modelado físico para contenedores.
*   `/Solar`, `/Eolica`, `/BESS`, etc.: Modelos específicos de fuentes.
*   `/GUI`: Aplicación Flask para control y monitoreo.
*   `/openspec`: Documentación spec-driven (proposal, design, tasks).

## Licencia
Este proyecto es para uso académico y de investigación. Se prohíbe su redistribución comercial sin autorización explícita.
