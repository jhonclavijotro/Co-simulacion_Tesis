"""Test P7: Validacion del protocolo de dinamica remota.

Verifica:
  1. Step con V_pcc opcional en servicio (test unitario _handle)
  2. Comando set_param en servicio
  3. Step remoto real con socket + cliente
  4. Compatibilidad hacia atras (step sin V_pcc)
  5. Multiples parametros en set_param

Uso:
    python Mockdata/test_p7_remote_protocol.py
"""

import sys; sys.path.insert(0, ".")

import json
import socket
import threading
import time


def _servir(svc, stop, ready):
    svc._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    svc._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    svc._server.bind(("127.0.0.1", 0))
    svc._server.listen(1)
    svc._server.settimeout(0.5)
    puerto = svc._server.getsockname()[1]
    ready["puerto"] = puerto
    ready["ok"] = True

    try:
        while not stop.is_set():
            try:
                conn, addr = svc._server.accept()
            except socket.timeout:
                continue
            with conn:
                conn.settimeout(5.0)
                buf = b""
                try:
                    while not stop.is_set():
                        datos = conn.recv(4096)
                        if not datos:
                            break
                        buf += datos
                        while b"\n" in buf:
                            linea, buf = buf.split(b"\n", 1)
                            if not linea.strip():
                                continue
                            req = json.loads(linea.decode("utf-8"))
                            resp = svc._handle(req)
                            conn.sendall(
                                (json.dumps(resp) + "\n").encode("utf-8")
                            )
                except (ConnectionResetError, BrokenPipeError):
                    pass
            break
    except Exception as e:
        ready["error"] = str(e)
    finally:
        try:
            svc._server.close()
        except Exception:
            pass
        svc._server = None


def _cliente_conectar(puerto):
    from MAS.cliente_dinamica import ClienteDinamica
    cli = ClienteDinamica(host="127.0.0.1", puerto=puerto, timeout=3.0)
    cli.conectar()
    return cli


def test_handle_step_con_vpcc():
    from Dinamica.servicio_dinamica import ServicioDinamica
    svc = ServicioDinamica("BESS", {"SoC": 0.6})
    resp = svc._handle({"comando": "step", "dt": 0.1,
                        "P_ref": 5000.0, "V_pcc": 110.0})
    assert resp.get("ok"), f"Step con V_pcc fallo: {resp}"
    assert "SoC" in resp
    print(f"  [PASS] _handle step con V_pcc: SoC={resp['SoC']:.4f}")
    return True


def test_handle_set_param():
    from Dinamica.servicio_dinamica import ServicioDinamica
    svc = ServicioDinamica("BESS", {"SoC": 0.6})
    resp = svc._handle({"comando": "set_param",
                        "params": {"eta_charge": 0.80, "eta_discharge": 0.85}})
    assert resp.get("ok"), f"set_param fallo: {resp}"
    assert svc.modelo.eta_charge == 0.80
    assert svc.modelo.eta_discharge == 0.85
    print(f"  [PASS] _handle set_param: eta_c={svc.modelo.eta_charge}")
    return True


def test_handle_comando_invalido():
    from Dinamica.servicio_dinamica import ServicioDinamica
    svc = ServicioDinamica("BESS", {"SoC": 0.6})
    resp = svc._handle({"comando": "invalid"})
    assert not resp.get("ok"), "Comando invalido debe retornar error"
    print(f"  [PASS] _handle comando invalido: error={resp.get('error')}")
    return True


def test_integracion_remota():
    from Dinamica.servicio_dinamica import ServicioDinamica

    svc = ServicioDinamica("BESS", {"SoC": 0.6}, host="127.0.0.1")
    stop = threading.Event()
    ready = {"ok": False}
    t = threading.Thread(target=_servir, args=(svc, stop, ready))
    t.daemon = True
    t.start()

    while not ready.get("ok"):
        time.sleep(0.05)

    cli = _cliente_conectar(ready["puerto"])

    resp1 = cli.step(0.1, 5000.0, V_pcc=110.0)
    assert resp1.get("ok"), f"Step remoto con V_pcc: {resp1}"

    resp2 = cli.step(0.1, -3000.0)
    assert resp2.get("ok"), f"Step remoto sin V_pcc: {resp2}"

    resp3 = cli.set_param(eta_charge=0.85)
    assert "eta_charge" in resp3.get("params_actualizados", [])

    cli.desconectar()
    stop.set()
    time.sleep(0.2)
    print(f"  [PASS] Integracion remota completa: "
          f"SoC1={resp1['SoC']:.4f}, SoC2={resp2['SoC']:.4f}")
    return True


if __name__ == "__main__":
    tests = [
        ("_handle step con V_pcc", test_handle_step_con_vpcc),
        ("_handle set_param", test_handle_set_param),
        ("_handle comando invalido", test_handle_comando_invalido),
        ("Integracion remota socket", test_integracion_remota),
    ]

    print("=" * 60)
    print("Test P7: Protocolo de Dinamica Remota")
    print("=" * 60)

    todos_ok = True
    for nombre, fn in tests:
        print(f"\n{nombre}:")
        try:
            ok = fn()
        except Exception as e:
            import traceback; traceback.print_exc()
            print(f"  [ERROR] {e}")
            ok = False
        todos_ok = todos_ok and ok

    print(f"\n{'=' * 60}")
    print(f"RESULTADO: {'TODOS PASARON' if todos_ok else 'FALLOS DETECTADOS'}")
    print(f"{'=' * 60}")
    sys.exit(0 if todos_ok else 1)
