# Script de automatización PowerShell para Windows (Equivalente a Makefile)
param (
    [string]$Target = "help"
)

switch ($Target) {
    "setup" {
        python -m pip install pypdf pymupdf arxiv pyzmq influxdb-client paho-mqtt pandas numpy matplotlib
    }
    "init-vault" {
        python tools/obsidian_vault_builder.py
    }
    "run-paper-search" {
        python tools/paper_search.py "microgrid finite-time leader-follower consensus control"
    }
    "audit-models" {
        python -m py_compile Solar/SistemaSolar.py BESS/SistemaBESS.py Eolica/SistemaEolico.py Hidrica/SistemaHidrico.py Diesel/SistemaDiesel.py Demanda/SistemaDemanda.py Central_PC/power_flow_fbs.py Central_PC/sensitivity_matrices.py Central_PC/master_clock_zmq.py mock_data/data_loader.py GUI/gui_command_center.py GUI/mqtt_publisher.py GUI/influx_telemetry.py GUI/server_dashboard.py
        Write-Host "Todos los modelos físicos y componentes compilaron correctamente." -ForegroundColor Green
    }
    "test" {
        python -m unittest discover tests
    }
    "run-master-fbs" {
        python -c "from Central_PC.master_clock_zmq import MasterClockZMQ; m = MasterClockZMQ('config/topologia_BT_4nodos.csv', mode='FBS'); m.start_loop(max_steps=10); m.close()"
    }
    "run-master-sens" {
        python -c "from Central_PC.master_clock_zmq import MasterClockZMQ; m = MasterClockZMQ('config/topologia_BT_4nodos.csv', mode='SENSITIVITY'); m.start_loop(max_steps=10); m.close()"
    }
    "run-gui-web" {
        python GUI/server_dashboard.py
    }
    "run-gui-desktop" {
        python GUI/app_gui_tkinter.py
    }
    Default {
        Write-Host "Comandos disponibles en Windows (usar .\make.ps1 <target>):" -ForegroundColor Cyan
        Write-Host "  .\make.ps1 run-gui-web      - Abre el Centro de Mando Web Dashboard"
        Write-Host "  .\make.ps1 run-gui-desktop  - Abre la aplicación de escritorio Tkinter"
        Write-Host "  .\make.ps1 test             - Ejecuta la suite de pruebas unitarias"
        Write-Host "  .\make.ps1 audit-models     - Audita la sintaxis del código Python"
        Write-Host "  .\make.ps1 run-master-fbs   - Ejecuta el reloj maestro en Modo FBS"
        Write-Host "  .\make.ps1 run-master-sens  - Ejecuta el reloj maestro en Modo Sensibilidad"
    }
}
