import pytest
import math
from common.network_channel_emulator import NetworkChannelEmulator
from Agents.network_impairment_proxy import NetworkImpairmentProxy

def test_ideal_channel():
    emulator = NetworkChannelEmulator(base_latency_ms=0.0, jitter_ms=0.0, loss_rate=0.0)
    payload = {"V": 1.02, "Q_ratio": 0.35}
    success, rx, lat = emulator.transmit(1, 2, payload)

    assert success is True
    assert rx == payload
    assert lat == 0.0

def test_latency_and_jitter():
    emulator = NetworkChannelEmulator(base_latency_ms=50.0, jitter_ms=10.0, loss_rate=0.0, seed=42)
    latencies = []
    for _ in range(500):
        success, rx, lat = emulator.transmit(1, 2, {"data": 1.0})
        assert success is True
        assert lat >= 0.0
        latencies.append(lat)

    avg_lat = sum(latencies) / len(latencies)
    # Media esperada ~ 50 ms (con margen de tolerancia estadística)
    assert 48.0 <= avg_lat <= 52.0

def test_bernoulli_packet_loss_rate():
    target_loss = 0.25
    emulator = NetworkChannelEmulator(loss_rate=target_loss, loss_model="bernoulli", seed=123)

    transmitted = 2000
    dropped = 0
    for _ in range(transmitted):
        success, rx, _ = emulator.transmit(1, 2, {"val": 10.0})
        if not success:
            dropped += 1

    empirical_loss = dropped / transmitted
    # Tolerancia estadística de +/- 0.03
    assert abs(empirical_loss - target_loss) < 0.03
    stats = emulator.get_statistics()
    assert abs(stats["packet_loss_ratio"] - target_loss) < 0.03

def test_gilbert_elliott_burst_loss():
    emulator = NetworkChannelEmulator(
        loss_model="gilbert_elliott",
        p_good_to_bad=0.1,
        p_bad_to_good=0.5,
        loss_in_bad=0.9,
        loss_in_good=0.01,
        seed=999
    )
    results = []
    for _ in range(1000):
        success, _, _ = emulator.transmit(1, 2, 1.0)
        results.append(success)

    # Debe haber tanto éxitos como pérdidas
    assert any(results)
    assert not all(results)
    stats = emulator.get_statistics()
    assert 0.05 <= stats["packet_loss_ratio"] <= 0.40

def test_noise_injection():
    emulator = NetworkChannelEmulator(noise_std=0.05, seed=777)
    payload = {"V": 1.0, "nested": {"Q": 5000.0}}
    success, rx, _ = emulator.transmit(1, 2, payload)

    assert success is True
    assert rx["V"] != 1.0
    assert abs(rx["V"] - 1.0) < 0.25
    assert rx["nested"]["Q"] != 5000.0

def test_link_outage_and_recovery():
    emulator = NetworkChannelEmulator()
    payload = {"status": "ok"}

    # Canal habilitado
    success, rx, _ = emulator.transmit(2, 3, payload)
    assert success is True

    # Cortar enlace
    emulator.set_link_state(2, 3, enabled=False)
    success_dropped, rx_none, _ = emulator.transmit(2, 3, payload)
    assert success_dropped is False
    assert rx_none is None

    # Restablecer enlace
    emulator.set_link_state(2, 3, enabled=True)
    success_restored, rx_restored, _ = emulator.transmit(2, 3, payload)
    assert success_restored is True
    assert rx_restored == payload

def test_async_message_queue():
    emulator = NetworkChannelEmulator(base_latency_ms=100.0, jitter_ms=0.0)
    current_time = 0.0

    # Enviar a t = 0.0 s, latencia = 100 ms -> entrega a t = 0.100 s
    emulator.enqueue_message(1, 2, {"step": 1}, current_time_s=current_time)

    # A t = 0.050 s, no debe haber mensajes listos
    ready_early = emulator.receive_ready_messages(current_time_s=0.050)
    assert len(ready_early) == 0

    # A t = 0.100 s, debe entregarse
    ready_ontime = emulator.receive_ready_messages(current_time_s=0.100)
    assert len(ready_ontime) == 1
    assert ready_ontime[0]["payload"]["step"] == 1

def test_proxy_profiles_and_scheduling():
    proxy = NetworkImpairmentProxy(profile="INDUSTRIAL_WIFI", seed=42)
    assert proxy.profile_name == "INDUSTRIAL_WIFI"
    assert proxy.emulator.loss_rate == 0.05

    # Programar corte de enlace entre nodos 2 y 3 para los pasos 5 a 7
    proxy.schedule_link_outage(u=2, v=3, start_step=5, duration_steps=3)

    raw_states = {3: {"V": 1.01, "Q_ratio": 0.3}}

    # Paso 4: Enlace activo
    filtered_4, meta_4 = proxy.filter_neighbor_states(receiver_id=2, raw_neighbor_states=raw_states, current_step=4)
    # Puede o no pasar por loss rate de WiFi (0.05), pero el enlace no está cortado

    # Paso 5: Enlace cortado forzosamente
    filtered_5, meta_5 = proxy.filter_neighbor_states(receiver_id=2, raw_neighbor_states=raw_states, current_step=5)
    assert 3 not in filtered_5
    assert meta_5["dropped"] == 1

    # Paso 8: Enlace restablecido
    proxy.emulator.loss_rate = 0.0  # Aislar corte programado
    filtered_8, _ = proxy.filter_neighbor_states(receiver_id=2, raw_neighbor_states=raw_states, current_step=8)
    assert 3 in filtered_8
