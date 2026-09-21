import csv
import os
from typing import Optional, Dict, List

class DockerComposeGenerator:
    """
    Generador paramétrico de manifiestos docker-compose.yml con desacoplamiento estricto.
    Genera 2 contenedores por nodo:
      - nodo_X_dinamica (Dockerfile.dynamic)
      - nodo_X_agente   (Dockerfile.agent)
    Soporta inyección de parámetros de canal de comunicación imperfecto (latencia, pérdida de paquetes y timeout).
    """
    def __init__(self, topology_csv: str, sources_map: Optional[Dict[int, str]] = None):
        self.topology_csv = topology_csv
        self.nodes: List[int] = []
        self.default_sources_map = {
            1: "DIESEL",
            2: "SOLAR",
            3: "EOLICA",
            4: "HIDRICA"
        }
        self.sources_map = sources_map if sources_map is not None else self.default_sources_map
        self.load_nodes()

    def load_nodes(self):
        nodes_set = set()
        with open(self.topology_csv, mode="r", encoding="utf-8") as f:
            valid_lines = [line for line in f if not line.strip().startswith("#")]
            reader = csv.DictReader(valid_lines)
            for row in reader:
                nodes_set.add(int(row["from_node"].strip()))
                nodes_set.add(int(row["to_node"].strip()))
        self.nodes = sorted(list(nodes_set))

    def generate_yaml(
        self,
        output_path: str = "docker-compose.yml",
        mode: str = "ONLINE",
        sources_map: Optional[Dict[int, str]] = None,
        network_profile: str = "IDEAL",
        network_delay_ms: float = 0.0,
        packet_loss_rate: float = 0.0,
        timeout_steps: int = 4,
        cpu_limit: str = "0.5",
        mem_limit: str = "256m",
        hold_mode: str = "ZOH",
        zfoh_lambda: float = 0.7,
        master_clock_host: str = "host.docker.internal"
    ) -> str:
        active_map = sources_map if sources_map is not None else self.sources_map
        
        yaml_lines = [
            "# Manifiesto Autogenerado de Co-Simulación Docker (Separación Estricta de Procesos y Emulación de Red)",
            "version: '3.8'",
            "",
            "networks:",
            "  microgrid_net:",
            "    driver: bridge",
            "",
            "services:"
        ]

        for n in self.nodes:
            source = active_map.get(n, "DEMANDA")
            
            # 1. Contenedor de Dinámica Física
            yaml_lines.extend([
                f"  nodo_{n}_dinamica:",
                "    build:",
                "      context: .",
                "      dockerfile: Docker/Dockerfile.dynamic",
                f"    container_name: nodo_{n}_dinamica",
                "    environment:",
                f"      - NODE_ID={n}",
                f"      - SOURCE_TYPE={source}",
                f"      - HOLD_MODE={hold_mode}",
                f"      - ZFOH_LAMBDA={zfoh_lambda}",
                f"      - MASTER_CLOCK_HOST={master_clock_host}",
                "    deploy:",
                "      resources:",
                "        limits:",
                f"          cpus: '{cpu_limit}'",
                f"          memory: {mem_limit}",
                "    networks:",
                "      - microgrid_net",
                ""
            ])

            # 2. Contenedor del Agente de Consenso
            yaml_lines.extend([
                f"  nodo_{n}_agente:",
                "    build:",
                "      context: .",
                "      dockerfile: Docker/Dockerfile.agent",
                f"    container_name: nodo_{n}_agente",
                "    environment:",
                f"      - NODE_ID={n}",
                f"      - OPERATING_MODE={mode}",
                f"      - NETWORK_PROFILE={network_profile}",
                f"      - NETWORK_DELAY_MS={network_delay_ms}",
                f"      - PACKET_LOSS_RATE={packet_loss_rate}",
                f"      - TIMEOUT_STEPS={timeout_steps}",
                f"      - HOLD_MODE={hold_mode}",
                f"      - ZFOH_LAMBDA={zfoh_lambda}",
                f"      - MASTER_CLOCK_HOST={master_clock_host}",
                "    deploy:",
                "      resources:",
                "        limits:",
                f"          cpus: '{cpu_limit}'",
                f"          memory: {mem_limit}",
                "    networks:",
                "      - microgrid_net",
                ""
            ])

        yaml_content = "\n".join(yaml_lines)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(yaml_content)
        
        return output_path

if __name__ == "__main__":
    top_file = os.path.join(os.path.dirname(__file__), "..", "config", "topologia_BT_4nodos.csv")
    gen = DockerComposeGenerator(top_file)
    out_yaml = gen.generate_yaml("docker-compose.test.yml", network_profile="INDUSTRIAL_WIFI", network_delay_ms=30.0, packet_loss_rate=0.05)
    print(f"Manifiesto docker-compose generado para {len(gen.nodes)} nodos ({len(gen.nodes)*2} contenedores) con perfil WiFi en: {out_yaml}")
