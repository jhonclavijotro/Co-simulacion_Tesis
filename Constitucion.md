# Constitucion del Proyecto: Sistema Multi-Agente para Microrred Distribuida

## 1. Delimitaciones del Proyecto

### 1.1 Alcance
Desarrollo de un Sistema Multi-Agente (MAS) para el control primario y secundario de tension y potencia reactiva en una microrred de baja tension conectada a la red principal, utilizando consenso lider-seguidor de tiempo finito.

### 1.2 Fuentes de Generacion
- Solar fotovoltaico (PV)
- Eolico
- Diesel
- Hidrico (derivado del modelo eolico)
- BESS (Battery Energy Storage System)
- Nodos de demanda (cargas)

### 1.3 Exclusiones
- No se implementaran modelos de calidad de potencia armonica
- No se incluye despacho economico ni mercado de energia
- La red de distribucion se modela como radial o debilmente mallada
- No se utilizaran librerias de flujo de potencia comerciales (Pandapower, OpenDSS)

## 2. Arquitectura de Software

### 2.1 Topologia de Despliegue
```
+------------------+     +------------------+     +------------------+
| Nodo Generacion  |     | Nodo Generacion  |     | Nodo Generacion  |
| [Dinamica]       |     | [Dinamica]       |     | [Dinamica]       |
| [Agente Consenso]|     | [Agente Consenso]|     | [Agente Consenso]|
+--------+---------+     +--------+---------+     +--------+---------+
         |                         |                         |
         +----------+--------------+-------------------------+
                    |              ZeroMQ                    |
         +----------+--------------+-------------------------+
         |                         |                         |
+--------+---------+     +--------+---------+     +---------+--------+
|   PC Central     |     |   GUI + InfluxDB |     |  Nodo Demanda    |
| [Master Clock]   |     | [Monitoreo]      |     | [Perfiles P,Q]   |
| [Sweep/Sens]     |     | [Carga datos]    |     |                  |
+------------------+     +------------------+     +------------------+
```

### 2.2 Separacion de Procesos
Cada nodo de generacion ejecuta **dos contenedores independientes**:
- **Contenedor A**: Dinamica de la fuente (modelo fisico)
- **Contenedor B**: Agente de consenso MAS (control distribuido)

Ambos contenedores se comunican via ZeroMQ.

### 2.3 Estructura del Repositorio
```
/
├── Constitucion.md
├── Tasks.md
├── Consultas.md
├── PLAN.md
├── Makefile
├── common/           # Modulos compartidos entre fuentes
│   ├── __init__.py
│   ├── Transformadas.py
│   ├── RedTrifasica.py
│   ├── GridInverter.py
│   ├── PMSG.py
│   ├── Rectificador.py
│   └── Graficadores.py
├── Solar/            # Modelo de generacion solar
│   ├── __init__.py
│   ├── SolarPanel.py
│   ├── MPPTController.py
│   ├── BoostConverter.py
│   └── SistemaSolar.py
├── Eolica/           # Modelo de generacion eolica
│   ├── __init__.py
│   ├── Aerogenerador.py
│   ├── PMSG.py
│   ├── Rectificador.py
│   └── SistemaEolico.py
├── Diesel/           # Modelo de generacion diesel
│   ├── __init__.py
│   ├── Diesel.py
│   └── SistemaDiesel.py
├── Hidrica/          # Modelo de generacion hidrocinetica
│   ├── __init__.py
│   ├── TurbinaHidrocinetica.py
│   └── SistemaHidrico.py
├── BESS/             # Modelo de almacenamiento
│   ├── __init__.py
│   └── ...
├── Demanda/          # Nodos de carga
│   ├── __init__.py
│   └── ...
├── Agents/           # Agentes de consenso MAS
│   ├── __init__.py
│   ├── consensus.py
│   └── local_agent.py
├── CentralPC/        # Simulador de red en PC central
│   ├── __init__.py
│   ├── master_clock.py
│   ├── solver_sweep.py
│   └── solver_sensitivity.py
├── GUI/              # Interfaz grafica de usuario
│   ├── __init__.py
│   └── ...
├── Docker/           # Archivos de contenerizacion
│   ├── docker-compose.yml
│   ├── Dockerfile.dinamica
│   └── Dockerfile.agente
└── Docs/             # Documentacion y referencias
    ├── index.rst
    └── *.pdf
```

## 3. Estandares de Codificacion

### 3.1 Lenguaje y Estilo
- Lenguaje: Python 3.11+
- Comentarios y documentacion: **espanol estandar**
- Nombres de variables, clases y funciones: **espanol o ingles** (consistente por modulo)
- Type hints obligatorios en funciones publicas

### 3.2 Nomenclatura
- Clases: PascalCase (ej. `SistemaSolar`, `RedTrifasica`)
- Metodos y variables: snake_case (ej. `calculate_output`, `duty_cycle`)
- Constantes: MAYUSCULAS (ej. `POA`, `V_DC_REF`)
- Archivos: PascalCase para clases principales

### 3.3 Prohibiciones
- No usar `from x import *`
- No usar variables globales mutables entre modulos
- No usar librerias de flujo de potencia comerciales (Pandapower, OpenDSS)

## 4. Comunicacion entre Procesos

### 4.1 Protocolos
- **ZeroMQ**: Sincronizacion maestro-esclavo entre PC Central y nodos
- **MQTT**: Publicacion de variables meteorologicas desde la GUI
- **InfluxDB**: Almacenamiento de datos historicos con discretizacion de 500 ms

### 4.2 Formato de Mensajes
Formato JSON con campos estandarizados:
```json
{
  "tipo": "setpoint|medicion|comando",
  "origen": "solar_01|eolica_01|...",
  "timestamp": 1234.567,
  "datos": { "V": 110.0, "P": 5000.0, "Q": 0.0 }
}
```

## 5. Control de Versiones

### 5.1 Ramas
- `main`: Estable, solo cambios revisados
- `develop`: Integracion de caracteristicas
- `feature/*`: Nuevas funcionalidades
- `fix/*`: Correccion de errores

### 5.2 Commits
Formato: `[tipo] mensaje descriptivo en espanol`
Tipos: `FEAT`, `FIX`, `REFACTOR`, `DOCS`, `TEST`, `CHORE`

## 6. Licencia
Uso academico y de investigacion. Prohibida su redistribucion comercial sin autorizacion.
