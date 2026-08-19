import csv
import os

class DockerComposeGenerator:
    """
    Generador paramétrico de manifiestos docker-compose.yml con desacoplamiento estricto.
    Genera 2 contenedores por nodo:
      - nodo_X_dinamica (Dockerfile.dynamic)
      - nodo_X_agente   (Dockerfile.agent)
    """
    def __init__(self, topology_csv, sources_map=None):
        self.topology_csv = topology_csv
        self.nodes = []
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

    def generate_yaml(self, output_path="docker-compose.yml", mode="ONLINE", sources_map=None):
        active_map = sources_map if sources_map is not None else self.sources_map
        
        yaml_lines = [
            "# Manifiesto Autogenerado de Co-Simulación Docker (Separación Estricta de Procesos)",
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
    out_yaml = gen.generate_yaml("docker-compose.test.yml")
    print(f"Manifiesto docker-compose generado para {len(gen.nodes)} nodos ({len(gen.nodes)*2} contenedores) en: {out_yaml}")
