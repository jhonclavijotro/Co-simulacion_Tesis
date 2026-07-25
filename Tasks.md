# Tablero Kanban - Sistema Multi-Agente para Microrred

## Instrucciones
- `[ ]` = Pendiente
- `[~]` = En progreso
- `[x]` = Completado

---

## FASE 0: Arquitectura y Gestion de Proyecto

| ID | Tarea | Estado | Prioridad |
|----|-------|--------|-----------|
| 0.1 | Crear `Constitucion.md` (delimitaciones, arquitectura, estandares) | [x] | Alta |
| 0.2 | Crear `Tasks.md` (tablero Kanban) | [x] | Alta |
| 0.3 | Crear `Consultas.md` (registro de literatura) | [x] | Alta |
| 0.4 | Crear `Makefile` (automatizacion de comandos) | [x] | Media |
| 0.5 | Crear `__init__.py` en todos los paquetes | [x] | Alta |

---

## FASE 1: Refactorizacion de Codigo Base

| ID | Tarea | Estado | Prioridad |
|----|-------|--------|-----------|
| 1.1 | Corregir imports invalidos (`from core.xxx` en Solar, Eolica, Diesel) | [x] | Critica |
| 1.2 | Corregir interfaz `SolarPanel.calculate_output` (args y retorno) | [x] | Critica |
| 1.3 | Corregir `SolarPanel._solve_panel_equation` (iteracion real Newton-Raphson) | [x] | Critica |
| 1.4 | Corregir `MPPTController` (logica P&O + agregar metodo `step()`) | [x] | Critica |
| 1.5 | Corregir `SistemaSolar.step` (args, metodos, tuple unpacking) | [x] | Critica |
| 1.6 | Corregir `SistemaEolico.step` (imports, `calcular_sistema`, tuples) | [x] | Critica |
| 1.7 | Corregir `SistemaDiesel.step` (imports, `convertir_torque_velocidad`, tuples) | [x] | Critica |
| 1.8 | Corregir `Aerogenerador.calcular_torque` (formula `0.5*rho*pi*R^2`) | [x] | Alta |
| 1.9 | Corregir `PMSG` (reemplazar `dstep` por integracion Euler) | [x] | Alta |
| 1.10 | Corregir `GridInverter.step` y `Rectificador.ejecutar` (retorno tuple) | [x] | Alta |
| 1.11 | Renombrar parametro `G` a `poa` en modelo solar | [x] | Media |
| 1.12 | Agregar `requirements.txt` y actualizar `Makefile` | [x] | Media |

---

## FASE 1.5: Nuevos Modelos de Generacion

| ID | Tarea | Estado | Prioridad |
|----|-------|--------|-----------|
| 1.13 | Crear modelo hidrocinetico (`Hidrica/`) a partir del eolico (rho_agua=1000) | [x] | Alta |

---

## FASE 2: Eliminacion de Duplicacion (DRY)

| ID | Tarea | Estado | Prioridad |
|----|-------|--------|-----------|
| 2.1 | Unificar `Transformadas.py` en `common/` | [x] | Alta |
| 2.2 | Unificar `RedTrifasica.py` en `common/` | [x] | Alta |
| 2.3 | Unificar `GridInverter.py` en `common/` | [x] | Alta |
| 2.4 | Unificar `Rectificador.py` en `common/` | [x] | Alta |
| 2.5 | Unificar `PMSG.py` en `common/` | [x] | Alta |
| 2.6 | Unificar graficadores en `common/` | [-] | Baja |

---

## FASE 3: Componentes del Sistema Multi-Agente

| ID | Tarea | Estado | Prioridad |
|----|-------|--------|-----------|
| 3.1 | Investigar e implementar nodo BESS | [x] | Alta |
| 3.2 | Crear nodo Hidrico (derivado del eolico) | [x] | Alta |
| 3.3 | Crear nodos de Demanda (perfiles P, Q) | [x] | Alta |
| 3.4 | Implementar PC Central - Modo A (Forward-Backward Sweep) | [x] | Alta |
| 3.5 | Implementar PC Central - Modo B (Matrices de Sensibilidad) | [x] | Alta |
| 3.6 | Desarrollar agentes de consenso MAS (tiempo finito) | [x] | Alta |
| 3.7 | Implementar comunicacion ZeroMQ (reloj maestro) | [x] | Alta |
| 3.7a | RelojZMQ: servidor TCP con PUB/PULL (stdlib socket+select) | [x] | Alta |
| 3.7b | AgenteZMQ: cliente TCP con SUB/PUSH (stdlib socket) | [x] | Alta |
| 3.7c | CoordinadorZMQ: orquestador distribuido con solver sweep | [x] | Alta |
| 3.7d | Script `ejecutar_agente.py` para lanzar agente por CLI | [x] | Alta |
| 3.7e | Test de comunicacion bidireccional (threads, 3 agentes + PC) | [x] | Alta |

---

## FASE 4: Contenerizacion y Despliegue

| ID | Tarea | Estado | Prioridad |
|----|-------|--------|-----------|
| 4.1 | Crear Dockerfile para dinamicas de generacion | [x] | Alta |
| 4.2 | Crear Dockerfile para agentes de consenso | [x] | Alta |
| 4.3 | Crear docker-compose.yml para orquestacion local | [x] | Alta |
| 4.4 | Motor de emulacion parametrico (N nodos base + M virtuales) | [x] | Alta |
| 4.5 | Servicio de dinamica remota (TCP/JSON para agente) | [x] | Alta |
| 4.6 | Cliente de dinamica para agente remoto | [x] | Alta |
| 4.7 | Script de despliegue deploy.py (SCP + SSH) | [x] | Media |
| 4.8 | Root docker-compose.yml para lanzamiento directo | [x] | Alta |
| 4.9 | Deploy en Raspberry Pi (SCP + Docker Compose) | [x] | Alta |
| 4.10 | Co-simulacion distribuida funcional: 3 dinamicas + 3 agentes + PC Central en RPi | [x] | Alta |

---

## FASE 5: GUI, Monitoreo y Persistencia

| ID | Tarea | Estado | Prioridad |
|----|-------|--------|-----------|
| 5.1 | Desarrollar GUI - Centro de Mando (carga de perfiles) | [x] | Alta |
| 5.2 | Integrar InfluxDB con discretizacion de 500 ms | [x] | Alta |
| 5.3 | Implementar publicacion MQTT de variables meteorologicas | [x] | Alta |
| 5.4 | Boton de despliegue "un clic" de contenedores | [x] | Media |
| 5.5 | CentralPC/logger_influx.py: escritura InfluxDB via HTTP API | [x] | Alta |
| 5.6 | CentralPC/climate_publisher.py: publicacion MQTT de meteo | [x] | Alta |
| 5.7 | GUI/app.py + templates/index.html: dashboard Flask + Chart.js | [x] | Alta |
| 5.8 | Docker/Dockerfile.gui: contenedor Flask + Gunicorn | [x] | Alta |
| 5.9 | docker-compose.full.yml: InfluxDB + Mosquitto + GUI + Logger | [x] | Alta |
| 5.10 | Perfiles de ejemplo (meteo + demanda) en GUI/data/ | [x] | Alta |

---

## FASE 6: Mejoras de Calidad

| ID | Tarea | Estado | Prioridad |
|----|-------|--------|-----------|
| 6.1 | Agregar type hints a todas las funciones | [ ] | Media |
| 6.2 | Estandarizar nomenclatura (espanol/ingles) | [ ] | Media |
| 6.3 | Reemplazar constantes literales por `np.pi` | [ ] | Baja |
| 6.4 | Eliminar saturacion fisica incorrecta en `decoupledC` | [ ] | Baja |
| 6.5 | Agregar pruebas unitarias para cada subsistema | [ ] | Media |
