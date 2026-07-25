# Tasks: Sistema Multi-Agente para Microrred Distribuida

Ver proyecto completo en Tasks.md (58 tareas originales).
Este archivo captura el estado actual en formato OpenSpec.

## FASE 0: Arquitectura y Gestion de Proyecto
- [x] **0.1** Crear Constitucion.md
- [x] **0.2** Crear Tasks.md
- [x] **0.3** Crear Consultas.md
- [x] **0.4** Crear Makefile
- [x] **0.5** Crear __init__.py en todos los paquetes

## FASE 1: Refactorizacion de Codigo Base
- [x] **1.1** Corregir imports invalidos (from core.xxx)
- [x] **1.2** Corregir interfaz SolarPanel.calculate_output
- [x] **1.3** Corregir SolarPanel._solve_panel_equation (Newton-Raphson)
- [x] **1.4** Corregir MPPTController (logica P&O + step())
- [x] **1.5** Corregir SistemaSolar.step
- [x] **1.6** Corregir SistemaEolico.step
- [x] **1.7** Corregir SistemaDiesel.step
- [x] **1.8** Corregir Aerogenerador.calcular_torque (0.5*rho*pi*R^2)
- [x] **1.9** Corregir PMSG (Euler en lugar de dstep)
- [x] **1.10** Corregir GridInverter.step y Rectificador.ejecutar
- [x] **1.11** Renombrar G a poa en modelo solar
- [x] **1.12** Agregar requirements.txt y actualizar Makefile

## FASE 2: DRY - Eliminacion de Duplicacion
- [x] **2.1-2.5** Unificar Transformadas, RedTrifasica, GridInverter, Rectificador, PMSG en common/
- [~] **2.6** Unificar graficadores en common/ (pendiente)

## FASE 3: Componentes MAS
- [x] **3.1** Implementar nodo BESS
- [x] **3.2** Crear nodo Hidrico
- [x] **3.3** Crear nodos de Demanda
- [x] **3.4** PC Central - Modo A (Forward-Backward Sweep)
- [x] **3.5** PC Central - Modo B (Matrices de Sensibilidad)
- [x] **3.6** Agentes de consenso MAS (tiempo finito)
- [x] **3.7** Comunicacion ZeroMQ (RelojZMQ, AgenteZMQ, CoordinadorZMQ, ejecutar_agente.py, test)

## FASE 4: Contenerizacion y Despliegue
- [x] **4.1-4.3** Dockerfiles (dinamica, agente) + docker-compose.yml
- [x] **4.4** Motor de emulacion parametrico (N+M nodos)
- [x] **4.5-4.6** Servicio dinamica remota + cliente
- [x] **4.7** deploy.py (SCP + SSH)
- [x] **4.8** Root docker-compose.yml
- [x] **4.9-4.10** Deploy RPi + co-simulacion 600 pasos verificada

## FASE 5: GUI, Monitoreo y Persistencia
- [x] **5.1-5.4** GUI Centro de Mando, InfluxDB, MQTT, boton deploy
- [x] **5.5-5.6** logger_influx.py, climate_publisher.py
- [x] **5.7** GUI/app.py + templates/index.html (Flask + Chart.js)
- [x] **5.8** Dockerfile.gui
- [x] **5.9** docker-compose.full.yml
- [x] **5.10** Perfiles de ejemplo (meteo + demanda)

## FASE 6: Mejoras de Calidad
- [x] **6.1** Type hints (MAS, CentralPC, Dinamica)
- [x] **6.2** Estandarizar nomenclatura
- [x] **6.3** math.pi -> np.pi
- [x] **6.4** decoupledC clamping eliminado
- [x] **6.5** tests/test_mas.py (24 tests, 23 pasan)

## FUTURO: Pendientes
- [ ] **F.1** ClienteMQTT con buffer circular
- [ ] **F.2** Integracion MQTT completa en simulacion
- [ ] **F.3** Extraccion parametros Rs/Rsh/n (Villalva)
- [ ] **F.4** PanelDatabase catalogo JSON
- [ ] **F.5** Refactor SolarPanel factory method
- [ ] **F.6** ArregloFotovoltaico + clima MQTT
- [ ] **F.7** Unificar graficadores
- [ ] **F.8** README.md
