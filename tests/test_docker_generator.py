import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Docker.docker_compose_generator import DockerComposeGenerator

class TestDockerGenerator(unittest.TestCase):

    def setUp(self):
        self.top_bt = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", "topologia_BT_4nodos.csv"))
        self.test_out = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "docker-compose.unittest.yml"))

    def tearDown(self):
        if os.path.exists(self.test_out):
            os.remove(self.test_out)

    def test_docker_compose_generation(self):
        gen = DockerComposeGenerator(self.top_bt)
        out_file = gen.generate_yaml(self.test_out, mode="ONLINE")
        self.assertTrue(os.path.exists(out_file))

        with open(out_file, mode="r", encoding="utf-8") as f:
            content = f.read()

        # Verificar que se generen 2 contenedores por cada uno de los 4 nodos (8 contenedores en total)
        for n in [1, 2, 3, 4]:
            self.assertIn(f"nodo_{n}_dinamica:", content)
            self.assertIn(f"nodo_{n}_agente:", content)

if __name__ == "__main__":
    unittest.main()
