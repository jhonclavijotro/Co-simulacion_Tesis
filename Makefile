# Makefile para Automatización del Proyecto Tesis MAS Microrred

PYTHON = python

.PHONY: help setup test-tools run-paper-search init-vault audit-models test run-master-fbs run-master-sens run-gui-web run-gui-desktop

help:
	@echo "Comandos disponibles:"
	@echo "  make setup            - Instala dependencias necesarias de Python"
	@echo "  make init-vault       - Inicializa la estructura de la Bóveda de Obsidian"
	@echo "  make run-paper-search - Busca artículos científicos relacionados en arXiv"
	@echo "  make audit-models     - Audita la sintaxis de todos los modelos del proyecto"
	@echo "  make test             - Ejecuta la suite de pruebas unitarias automatizadas"
	@echo "  make run-master-fbs   - Ejecuta el reloj maestro en Modo A (Forward-Backward Sweep)"
	@echo "  make run-master-sens  - Ejecuta el reloj maestro en Modo B (Matrices de Sensibilidad)"
	@echo "  make run-gui-web      - Abre el Centro de Mando Web Dashboard en http://localhost:8080/web_dashboard.html"
	@echo "  make run-gui-desktop  - Abre la aplicación de escritorio Tkinter GUI"

setup:
	$(PYTHON) -m pip install pypdf pymupdf arxiv pyzmq influxdb-client paho-mqtt pandas numpy matplotlib

init-vault:
	$(PYTHON) tools/obsidian_vault_builder.py

run-paper-search:
	$(PYTHON) tools/paper_search.py "microgrid finite-time leader-follower consensus control"

audit-models:
	$(PYTHON) -m py_compile Solar/SistemaSolar.py BESS/SistemaBESS.py Eolica/SistemaEolico.py Hidrica/SistemaHidrico.py Diesel/SistemaDiesel.py Demanda/SistemaDemanda.py Central_PC/power_flow_fbs.py Central_PC/sensitivity_matrices.py Central_PC/master_clock_zmq.py mock_data/data_loader.py GUI/gui_command_center.py GUI/mqtt_publisher.py GUI/influx_telemetry.py
	@echo "Todos los modelos físicos, solucionadores y componentes GUI compilaron correctamente."

test:
	$(PYTHON) -m unittest discover tests

run-master-fbs:
	$(PYTHON) -c "from Central_PC.master_clock_zmq import MasterClockZMQ; m = MasterClockZMQ('config/topologia_BT_4nodos.csv', mode='FBS'); m.start_loop(max_steps=10); m.close()"

run-master-sens:
	$(PYTHON) -c "from Central_PC.master_clock_zmq import MasterClockZMQ; m = MasterClockZMQ('config/topologia_BT_4nodos.csv', mode='SENSITIVITY'); m.start_loop(max_steps=10); m.close()"

run-gui-web:
	$(PYTHON) GUI/server_dashboard.py

run-gui-desktop:
	$(PYTHON) GUI/app_gui_tkinter.py
