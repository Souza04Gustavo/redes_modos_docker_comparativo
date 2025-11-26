
import subprocess
import json
import time
import pandas as pd
import matplotlib.pyplot as plt
import os
import numpy as np
import seaborn as sns

# --- CONFIGURAÇÕES GERAIS ---
IMAGE_NAME = "rec_te1_container"
PROJECT_NAME = "REC_TE1"
RESULTS_DIR = "resultados_essenciais"
TEST_DURATION = 30      # 30s é o padrão ouro para estabilidade
IPERF_RUNS = 3          # 3 rodadas são suficientes para média
NETPERF_SAMPLES = 30    # Amostras para o Boxplot

os.makedirs(RESULTS_DIR, exist_ok=True)

# --- FUNÇÕES AUXILIARES ---
def run_cmd(cmd):
    print(f"[EXEC] {cmd}")
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout

def setup_server(mode):
    print(f"\n--- Configurando Servidor: {mode.upper()} ---")
    run_cmd("docker rm -f rec_server")
    net_flag = "--net=host" if mode == "host" else f"--network {mode}"
    run_cmd(f"docker run -d --rm --name rec_server {net_flag} {IMAGE_NAME}")
    time.sleep(3) # Espera subir
    run_cmd("docker exec -d rec_server iperf3 -s")
    run_cmd("docker exec -d rec_server netserver")
    time.sleep(2)

def get_target_ip(mode):
    if mode == "host": return "localhost"
    return run_cmd("docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' rec_server").strip()

# --- COLETA ---
def collect_throughput_cpu(mode, target_ip):
    """Roda Iperf TCP várias vezes e coleta Vazão (série temporal) e CPU média."""
    runs_throughput = []
    runs_cpu = []
    
    for i in range(IPERF_RUNS):
        print(f"   -> Rodada TCP {i+1}/{IPERF_RUNS}...")
        net_flag = "--net=host" if mode == "host" else "--network bridge"
        # --json permite pegar CPU e Vazão
        cmd = f"docker run --rm {net_flag} {IMAGE_NAME} iperf3 -c {target_ip} -t {TEST_DURATION} --json"
        try:
            data = json.loads(run_cmd(cmd))
            
            # 1. Vazão segundo a segundo (para o Gráfico de Linha)
            intervals = [x['sum']['bits_per_second']/1e9 for x in data['intervals']]
            runs_throughput.append(intervals[:TEST_DURATION])
            
            # 2. CPU Total (Host + Remote) média dessa rodada (para o Gráfico de Barras)
            cpu_host = data['end']['cpu_utilization_percent']['host_total']
            cpu_remote = data['end']['cpu_utilization_percent']['remote_total']
            runs_cpu.append(cpu_host + cpu_remote)
            
        except Exception as e:
            print(f"   [ERRO] Falha na rodada {i+1}: {e}")

    return runs_throughput, np.mean(runs_cpu) if runs_cpu else 0

def collect_latency(mode, target_ip):
    """Roda Netperf várias vezes para o Boxplot."""
    print(f"   -> Coletando {NETPERF_SAMPLES} amostras de latência...")
    net_flag = "--net=host" if mode == "host" else "--network bridge"
    samples = []
    for _ in range(NETPERF_SAMPLES):
        cmd = f"docker run --rm {net_flag} {IMAGE_NAME} netperf -H {target_ip} -t TCP_RR -l 1 -- -o P99_LATENCY"
        try:
            res = run_cmd(cmd).strip().splitlines()[-1]
            samples.append(float(res))
        except: pass
    return samples

def collect_udp_quality(mode, target_ip):
    """Roda Iperf UDP uma vez para ver Jitter e Perda."""
    print(f"   -> Teste de Stress UDP...")
    net_flag = "--net=host" if mode == "host" else "--network bridge"
    # -b 0 = banda ilimitada (stress test)
    cmd = f"docker run --rm {net_flag} {IMAGE_NAME} iperf3 -c {target_ip} -t 10 -u -b 0 --json"
    try:
        data = json.loads(run_cmd(cmd))
        return {
            'jitter': data['end']['sum']['jitter_ms'],
            'loss': data['end']['sum']['lost_percent']
        }
    except: return {'jitter': 0, 'loss': 0}

# --- PLOTAGEM (OS 4 GRÁFICOS ESSENCIAIS) ---
def plot_essentials(db):
    print("\n--- Gerando os 4 Gráficos Essenciais ---")
    sns.set_style("whitegrid")
    colors = {'host': '#1f77b4', 'bridge': '#ff7f0e', 'overlay': '#2ca02c', 'macvlan': '#d62728'}
    modes = list(db.keys())

    # GRÁFICO 1: Estabilidade (Linha com Sombra)
    plt.figure(figsize=(10, 6))
    for m in modes:
        runs = db[m]['throughput_runs']
        if not runs: continue
        # Ajusta matriz para o menor tamanho comum (caso alguma rodada tenha falhado)
        min_len = min(len(r) for r in runs)
        arr = np.array([r[:min_len] for r in runs])
        
        mean = np.mean(arr, axis=0)
        std = np.std(arr, axis=0)
        t = np.arange(1, len(mean)+1)
        
        plt.plot(t, mean, label=f"{m.upper()}", color=colors.get(m), linewidth=2)
        plt.fill_between(t, mean-std, mean+std, color=colors.get(m), alpha=0.2)
    
    plt.title("1. Estabilidade da Vazão (Média e Variação)")
    plt.xlabel("Tempo (s)")
    plt.ylabel("Vazão (Gbps)")
    plt.legend(loc='lower right')
    plt.savefig(f"{RESULTS_DIR}/1_estabilidade.png")
    print("-> 1_estabilidade.png salvo.")

    # GRÁFICO 2: Eficiência (Vazão vs CPU) - Eixo Duplo
    fig, ax1 = plt.subplots(figsize=(10, 6))
    x = np.arange(len(modes))
    width = 0.35
    
    # Dados
    avg_throughputs = [np.mean(db[m]['throughput_runs']) if db[m]['throughput_runs'] else 0 for m in modes]
    avg_cpus = [db[m]['cpu_avg'] for m in modes]
    
    # Barras Vazão
    ax1.bar(x - width/2, avg_throughputs, width, label='Vazão (Gbps)', color='#1f77b4', alpha=0.8)
    ax1.set_ylabel('Vazão (Gbps)', color='#1f77b4', fontweight='bold')
    ax1.tick_params(axis='y', labelcolor='#1f77b4')
    ax1.set_title("2. Eficiência: Vazão Máxima vs Custo de CPU")
    
    # Barras CPU
    ax2 = ax1.twinx()
    ax2.bar(x + width/2, avg_cpus, width, label='Uso CPU (%)', color='#d62728', alpha=0.8)
    ax2.set_ylabel('Uso CPU Total (%)', color='#d62728', fontweight='bold')
    ax2.tick_params(axis='y', labelcolor='#d62728')
    
    ax1.set_xticks(x)
    ax1.set_xticklabels([m.upper() for m in modes])
    plt.savefig(f"{RESULTS_DIR}/2_eficiencia.png")
    print("-> 2_eficiencia.png salvo.")

    # GRÁFICO 3: Latência (Boxplot)
    plt.figure(figsize=(8, 6))
    data_lat = [db[m]['latency_samples'] for m in modes if db[m]['latency_samples']]
    labels_lat = [m.upper() for m in modes if db[m]['latency_samples']]
    
    plt.boxplot(data_lat, tick_labels=labels_lat, patch_artist=True, 
                boxprops=dict(facecolor="lightblue"))
    plt.title("3. Latência Transacional (Distribuição)")
    plt.ylabel("Tempo de Resposta (microssegundos)")
    plt.grid(True, axis='y')
    plt.savefig(f"{RESULTS_DIR}/3_latencia.png")
    print("-> 3_latencia.png salvo.")

    # GRÁFICO 4: Qualidade UDP (Jitter e Perda)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    jitters = [db[m]['udp']['jitter'] for m in modes]
    losses = [db[m]['udp']['loss'] for m in modes]
    
    ax1.bar(modes, jitters, color='purple', alpha=0.7)
    ax1.set_title("Jitter (Instabilidade)")
    ax1.set_ylabel("ms")
    
    ax2.bar(modes, losses, color='red', alpha=0.7)
    ax2.set_title("Perda de Pacotes")
    ax2.set_ylabel("% Perdido")
    
    plt.suptitle("4. Qualidade de Rede em Tempo Real (UDP)")
    plt.savefig(f"{RESULTS_DIR}/4_qualidade_udp.png")
    print("-> 4_qualidade_udp.png salvo.")


# --- MAIN ---
def main():
    modes = ["host", "bridge"] # Adicione outros aqui quando for testar
    database = {}

    try:
        for mode in modes:
            setup_server(mode)
            target = get_target_ip(mode)
            
            tp_runs, cpu = collect_throughput_cpu(mode, target)
            lat_samples = collect_latency(mode, target)
            udp_stats = collect_udp_quality(mode, target)
            
            database[mode] = {
                'throughput_runs': tp_runs,
                'cpu_avg': cpu,
                'latency_samples': lat_samples,
                'udp': udp_stats
            }
            
            run_cmd("docker rm -f rec_server")
            
        plot_essentials(database)
        print(f"\n[FIM] Resultados em: {RESULTS_DIR}")

    except KeyboardInterrupt:
        run_cmd("docker rm -f rec_server")

if __name__ == "__main__":
    main()
