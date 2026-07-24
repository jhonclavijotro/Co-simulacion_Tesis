# Makefile - Sistema Multi-Agente para Microrred Distribuida
# Comandos de automatizacion para desarrollo y simulacion

.PHONY: help install clean run-solar run-eolica run-diesel run-all lint typecheck docs

help:
	@echo "Comandos disponibles:"
	@echo "  make install       - Instala dependencias (numpy, scipy, matplotlib)"
	@echo "  make help          - Muestra esta ayuda"
	@echo "  make run-solar     - Ejecuta simulacion del sistema solar"
	@echo "  make run-eolica    - Ejecuta simulacion del sistema eolico"
	@echo "  make run-diesel    - Ejecuta simulacion del sistema diesel"
	@echo "  make run-all       - Ejecuta todas las simulaciones"
	@echo "  make clean         - Elimina archivos temporales y __pycache__"
	@echo "  make lint          - Ejecuta ruff (linter) sobre el codigo"
	@echo "  make typecheck     - Ejecuta mypy (type checker)"
	@echo "  make docs          - Genera documentacion con Sphinx"

install:
	pip install -r requirements.txt

run-solar:
	python -m Solar.SistemaSolar

run-eolica:
	python -m Eolica.SistemaEolico

run-diesel:
	python -m Diesel.SistemaDiesel

run-hidrica:
	python -m Hidrica.SistemaHidrico

run-all: run-solar run-eolica run-diesel

clean:
	@echo "Eliminando archivos temporales..."
	-rmdir /s /q Solar\__pycache__ 2>nul
	-rmdir /s /q Eolica\__pycache__ 2>nul
	-rmdir /s /q Diesel\__pycache__ 2>nul
	-rmdir /s /q common\__pycache__ 2>nul
	-del /q *.csv 2>nul
	@echo "Limpieza completada."

lint:
	@echo "Ejecutando linter..."
	ruff check .

typecheck:
	@echo "Ejecutando type checker..."
	mypy .

docs:
	@echo "Generando documentacion..."
	cd Docs && sphinx-build -b html . _build
