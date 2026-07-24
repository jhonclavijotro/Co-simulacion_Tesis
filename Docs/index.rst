.. Documentación del Sistema Multi-Agente para Microrred

Documentación del Sistema Multi-Agente (MAS)
================================================

Bienvenido a la documentación oficial del Sistema Multi-Agente (MAS) para el control primario y secundario (consenso de tiempo finito) de tensión y potencia reactiva en microrredes de baja tensión.

.. toctree::
   :maxdepth: 2
   :caption: Contenido:

   introduccion
   arquitectura
   modulos

Módulos del Sistema
-------------------

.. automodule:: src.common.messages
   :members:
   :undoc-members:

.. automodule:: src.common.zmq_utils
   :members:
   :undoc-members:

.. automodule:: src.microgrid.topology
   :members:
   :undoc-members:

.. automodule:: src.agents.consensus
   :members:
   :undoc-members:

.. automodule:: src.agents.local_agent
   :members:
   :undoc-members:

.. automodule:: src.central_pc.master_clock
   :members:
   :undoc-members:

.. automodule:: src.central_pc.solver_pandapower
   :members:
   :undoc-members:

.. automodule:: src.central_pc.solver_sensitivity
   :members:
   :undoc-members:
