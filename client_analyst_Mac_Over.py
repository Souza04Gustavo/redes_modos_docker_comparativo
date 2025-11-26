import subprocess
import json
import time
import pandas as pd
import matplotlib.pyplot as plt
import os
import numpy as np
import seaborn as sns
import sys

# --- CONFIGURAÇÕES (EDITAR) ---
PARENT_INTERFACE = "wlp0s20f3"      # Sua interface Wi-Fi
SUBNET = "192.168.127.0/24"         # Sua faixa de IP correta
GATEWAY = "192.168.127.1"
# IP Fixo para o container Cliente
MACVLAN_CLIENT_IP = "192.168.127.201"
# IP onde o Servidor está (definido no script anterior)
TARGET_IP_MACVLAN = "192.168.127.200"

IMAGE_NAME = "rec_te1_container"
RESULTS_DIR = "resultados_multihost"
TEST_DURATION = 60
IPERF_RUNS = 5
NETPERF_SAMPLES = 30

os.makedirs(RESULTS_DIR, exist_ok=True)

def run_cmd_output(cmd):
    print(f"[EXEC] {cmd}")
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout

def run_cmd(cmd):
    print(f"[EXEC] {cmd}")
    subprocess.run(cmd, shell=True, check=False)

def setup_client_env(mode):
    run_cmd("docker rm -f rec_client")
    
    if mode == 'macvlan':
        # Recria a rede localmente usando IPVLAN (Compatível com Wi-Fi)
        run_cmd("docker network rm rede_macvlan_manual")
        
        # MUDANÇA AQUI: Trocamos -d macvlan por -d ipvlan e adicionamos ipvlan_mode=l2
        cmd_net = (f"docker network create -d ipvlan "
                   f"--subnet={SUBNET} --gateway={GATEWAY} "
                   f"-o parent={PARENT_INTERFACE} -o ipvlan_mode=l2 "
                   f"rede_macvlan_manual")
        run_cmd(cmd_net)
        
        # Sobe cliente
        run_cmd(f"docker run -d --rm --name rec_client --network rede_macvlan_manual --ip {MACVLAN_CLIENT_IP} {IMAGE_NAME} tail -f /dev/null")
        return TARGET_IP_MACVLAN    
        
    elif mode == 'overlay':
        # No overlay, o Swarm já propagou a rede. Só conecta.
        run_cmd(f"docker run -d --rm --name rec_client --network rede_overlay_manual {IMAGE_NAME} tail -f /dev/null")
        return "rec_server" # DNS do Docker Swarm

# --- COLETA DE DADOS (Idêntica ao script anterior) ---
def collect_metrics(target_ip):
    # 1. Vazão TCP e CPU
    runs_throughput = []
    runs_cpu = []
    for i in range(IPERF_RUNS):
        print(f"   -> Iperf TCP ({i+1}/{IPERF_RUNS})...")
        cmd = f"docker exec rec_client iperf3 -c {target_ip} -t {TEST_DURATION} --json"
        try:
            data = json.loads(run_cmd_output(cmd))
            intervals = [x['sum']['bits_per_second']/1e9 for x in data['intervals']]
            runs_throughput.append(intervals[:TEST_DURATION])
            cpu_total = data['end']['cpu_utilization_percent']['host_total'] + data['end']['cpu_utilization_percent']['remote_total']
            runs_cpu.append(cpu_total)
        except Exception as e: print(f"Erro TCP: {e}")

    # 2. Latência
    print(f"   -> Netperf Latência...")
    lat_samples = []
    for _ in range(NETPERF_SAMPLES):
        cmd = f"docker exec rec_client netperf -H {target_ip} -t TCP_RR -l 1 -- -o P99_LATENCY"
        try:
            res = run_cmd_output(cmd).strip().splitlines()[-1]
            lat_samples.append(float(res))
        except: pass

    # 3. UDP
    print(f"   -> Iperf UDP...")
    cmd = f"docker exec rec_client iperf3 -c {target_ip} -t 10 -u -b 0 --json"
    udp_data = {'jitter': 0, 'loss': 0}
    try:
        data = json.loads(run_cmd_output(cmd))
        udp_data['jitter'] = data['end']['sum']['jitter_ms']
        udp_data['loss'] = data['end']['sum']['lost_percent']
    except: pass

    return {
        'throughput_runs': runs_throughput,
        'cpu_avg': np.mean(runs_cpu) if runs_cpu else 0,
        'latency_samples': lat_samples,
        'udp': udp_data
    }

# --- PLOTAGEM ---
def generate_charts(db):
    print("\n--- Gerando Gráficos Multi-Host ---")
    sns.set_style("whitegrid")
    colors = {'macvlan': '#d62728', 'overlay': '#2ca02c'}
    modes = list(db.keys())

    # 1. Estabilidade
    plt.figure(figsize=(10, 6))
    for m in modes:
        runs = db[m]['throughput_runs']
        if not runs: continue
        min_len = min(len(r) for r in runs)
        arr = np.array([r[:min_len] for r in runs])
        mean = np.mean(arr, axis=0)
        std = np.std(arr, axis=0)
        t = np.arange(1, len(mean)+1)
        plt.plot(t, mean, label=f"{m.upper()}", color=colors.get(m), linewidth=2)
        plt.fill_between(t, mean-std, mean+std, color=colors.get(m), alpha=0.2)
    plt.title("Multi-Host: Estabilidade da Vazão")
    plt.xlabel("Tempo (s)"); plt.ylabel("Gbps")
    plt.legend(); plt.savefig(f"{RESULTS_DIR}/1_multihost_vazao.png")

    # 2. Eficiência
    fig, ax1 = plt.subplots(figsize=(10, 6))
    x = np.arange(len(modes)); width = 0.35
    avg_tp = [np.mean(db[m]['throughput_runs']) if db[m]['throughput_runs'] else 0 for m in modes]
    avg_cpu = [db[m]['cpu_avg'] for m in modes]
    
    ax1.bar(x - width/2, avg_tp, width, label='Vazão (Gbps)', color='#1f77b4')
    ax1.set_ylabel('Vazão', color='#1f77b4')
    ax2 = ax1.twinx()
    ax2.bar(x + width/2, avg_cpu, width, label='CPU Total (%)', color='#ff7f0e')
    ax2.set_ylabel('CPU (%)', color='#ff7f0e')
    ax1.set_xticks(x); ax1.set_xticklabels([m.upper() for m in modes])
    plt.title("Multi-Host: Eficiência")
    plt.savefig(f"{RESULTS_DIR}/2_multihost_eficiencia.png")

    # 3. Latência
    plt.figure(figsize=(8, 6))
    data_lat = [db[m]['latency_samples'] for m in modes if db[m]['latency_samples']]
    labels = [m.upper() for m in modes if db[m]['latency_samples']]
    plt.boxplot(data_lat, tick_labels=labels, patch_artist=True)
    plt.title("Multi-Host: Latência (P99)")
    plt.ylabel("µs")
    plt.savefig(f"{RESULTS_DIR}/3_multihost_latencia.png")

    # 4. UDP
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    jit = [db[m]['udp']['jitter'] for m in modes]
    loss = [db[m]['udp']['loss'] for m in modes]
    ax1.bar(modes, jit, color='purple'); ax1.set_title("Jitter")
    ax2.bar(modes, loss, color='red'); ax2.set_title("Perda %")
    plt.savefig(f"{RESULTS_DIR}/4_multihost_udp.png")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Modo de uso: python3 client_analyst.py [teste_que_deseja_fazer]")
        print("Exemplo: python3 client_analyst.py macvlan")
        print("Nota: Você deve rodar um modo por vez, após configurar o servidor.")
        sys.exit(1)

    mode_atual = sys.argv[1] # 'macvlan' ou 'overlay'
    
    # Verifica se já temos dados salvos para não sobrescrever se rodarmos separado
    db_file = f"{RESULTS_DIR}/db_temp.json"
    if os.path.exists(db_file):
        with open(db_file, 'r') as f: database = json.load(f)
    else:
        database = {}

    print(f"--- Iniciando Testes para: {mode_atual.upper()} ---")
    target = setup_client_env(mode_atual)
    time.sleep(5) # Espera conexão firmar
    
    # Coleta
    metrics = collect_metrics(target)
    database[mode_atual] = metrics
    
    # Salva banco de dados temporário
    with open(db_file, 'w') as f: json.dump(database, f)
    
    # Limpeza
    run_cmd("docker rm -f rec_client")
    
    # Se já tivermos os dois modos no banco de dados, gera os gráficos comparativos
    if 'macvlan' in database and 'overlay' in database:
        generate_charts(database)
        print("\n[SUCESSO] Gráficos comparativos gerados!")
    else:
        print(f"\n[OK] Dados de {mode_atual} salvos. Agora rode o teste para o outro modo para gerar os gráficos.")