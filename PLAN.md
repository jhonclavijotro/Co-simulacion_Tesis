# Prompt Maestro V4: Implementación de Sistema Multi-Agente (MAS) para Microrred Distribuida

## 1. Contexto y Rol del Agente
Actúa como un Ingeniero de Software experto en Sistemas de Potencia, arquitecturas distribuidas (ZeroMQ, MQTT), despliegue en contenedores (Docker) y desarrollo de interfaces.
El objetivo del proyecto es desarrollar un Sistema Multi-Agente (MAS) para el control primario y secundario (consenso líder-seguidor de tiempo finito) de una microrred conectada a la red principal. Los agentes deben estabilizarse de manera completamente independiente a través del consenso para regular la tensión y el reparto de potencia reactiva, sin depender de un coordinador central.

## 2. Herramientas MCP y Gestión del Conocimiento (Obligatorio)
Tienes acceso a un folder llamado **Docs** que contiene documentación relevante para el desarrollo del proyecto, así como herramientas MCP para consultar **arXiv** y **NotebookLM**. Debes utilizarlas obligatoriamente antes de implementar cualquier modelo matemático (ej. extracción de matrices de sensibilidad, método de barrido para flujo de potencia, modelos de baterías BESS, o algoritmos de consenso).
* **Registro de Consultas:** Todo modelo matemático implementado debe estar respaldado por la literatura extraída de estas herramientas. Debes registrar cada documento utilizado en un archivo `Consultas.md` utilizando formato APA y su respectivo DOI.

## 3. Arquitectura de Hardware y Contenedores Docker (Aislamiento Modular)
El sistema se desplegará en un clúster de hardware distribuido (Raspberry Pi 5) y un PC Central. La contenerización debe ser estrictamente modular y desacoplada:
* **Separación Estricta de Procesos:** En cada nodo de generación, el modelo de simulación de la dinámica de la fuente y el agente de consenso NO deben coexistir en el mismo contenedor. Debes generar un `Dockerfile` independiente para la dinámica de generación y otro para el agente.
* **Topología Base y Expansión:** El hardware emulará nodos físicos de generación (Solar, Eólico, Hídrico, Diésel, BESS) y un nodo dedicado a la publicación de datos. 
* **Escalabilidad Paramétrica:** El motor de emulación de la red en el PC Central debe ser paramétrico, escalando fluidamente desde una topología de 4 nodos base hasta emular $N$ nodos físicos de generación y $M$ nodos virtuales de demanda.

## 4. Orquestación y Despliegue Dinámico desde la GUI
Se debe desarrollar una Interfaz Gráfica de Usuario (GUI) conectada a InfluxDB (con discretización de 500 ms) que actúe como **Centro de Mando**:
* **Carga de Archivos:** Permitir al usuario subir perfiles de demanda y series temporales meteorológicas en `.csv` o `.xlsx`.
* **Inyección MQTT:** Las variables meteorológicas se publicarán vía MQTT a los nodos correspondientes.
* **Despliegue Controlado:** La GUI debe permitir seleccionar qué fuentes participarán y, mediante un solo clic, orquestar el despliegue automático de los contenedores correspondientes (dinámicas y agentes) en sus plataformas.

## 5. Modelado Físico de Componentes
* **Revisión de Códigos Base (Solar y Diésel):** Se suministrarán modelos dinámicos base. Debes auditarlos y refactorizarlos para garantizar su modularidad.
* **Generación Eólica e Hídrica:** Toma en cuenta el modelo eólico suministrado y modifícalo para construir el nodo hídrico. Ambos comparten la misma dinámica base; tu tarea es unificar la estructura paramétrica y diferenciar el cálculo modificando la densidad del fluido.
* **Nodo BESS (Almacenamiento):** Realiza una investigación profunda (vía MCP) sobre cómo implementar en código Python un sistema BESS conectado a red mediante un inversor electrónico. Prioriza adaptar los modelos de inversor electrónico ya desarrollados/suministrados para acoplar la dinámica de la batería. Si no es posible la adaptación, modela uno nuevo específico para esta aplicación.
* **Nodos de Demanda:** Construye la lógica necesaria para el despliegue de las cargas. Ten en cuenta que estos nodos no tienen dinámica de generación; el modelo debe limitarse a leer y procesar estrictamente los datos de potencia activa ($P$) y potencia reactiva ($Q$) demandada en cada nodo a partir de los perfiles cargados.

## 6. Simulación del Entorno Eléctrico (PC Central)
El PC central actuará como un reloj maestro sincronizado vía ZeroMQ. Debes desarrollar dos ramas de ejecución seleccionables, **desarrollando los modelos matemáticos desde cero** (prohibido el uso de librerías como Pandapower):
* **Modo A (Co-simulación Multitasa - Forward-Backward Sweep):** Implementa un solucionador propio utilizando el algoritmo *Forward-Backward Sweep* (Barrido Iterativo). Este algoritmo leerá un `.csv` con los parámetros de la red ($R, X, d$) para resolver la topología radial/débilmente mallada en cada paso maestro.
* **Modo B (Matrices de Sensibilidad):** Aplica una linealización del sistema alrededor de un estado estable para evaluar variaciones climáticas suaves mediante multiplicaciones matriciales directas ($\Delta V = S_{VQ}\Delta Q$).

## 7. Archivos de Control de Proyecto
Antes de iniciar la codificación, estructura en la raíz del proyecto:
1. `Constitucion.md`: Delimitaciones, arquitectura de software y estándares.
2. `Tasks.md`: Tablero Kanban en texto para seguimiento de tareas.
3. `Consultas.md`: Registro de literatura científica (paso 2).
4. `Makefile`: Automatización de comandos.