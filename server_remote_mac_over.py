import subprocess
import time
import sys

# --- CONFIGURAÇÕES DE REDE ---
PARENT_INTERFACE = "wlp0s20f3"
SUBNET = "192.168.100.0/24"
GATEWAY = "192.168.100.1"
# Usando IP Range para evitar conflitos com DHCP da casa
IP_RANGE = "192.168.100.192/27"
MACVLAN_SERVER_IP = "192.168.100.200"

IMAGE_NAME = "rec_te1_container"

def run_cmd(cmd, ignore_error=False):
    print(f"[EXEC] {cmd}")
    try:
        subprocess.run(cmd, shell=True, check=not ignore_error)
    except subprocess.CalledProcessError:
        print(f"\n[ERRO CRÍTICO] O comando falhou: {cmd}")
        print("Verifique o erro acima e tente corrigir.")
        sys.exit(1)

def setup_macvlan():
    print("\n--- Configurando MACVLAN (Servidor) ---")
    run_cmd("docker rm -f rec_server", ignore_error=True)
    run_cmd("docker network rm rede_macvlan_manual", ignore_error=True)
    
    cmd_net = (f"docker network create -d macvlan "
               f"--subnet={SUBNET} --gateway={GATEWAY} --ip-range={IP_RANGE} "
               f"-o parent={PARENT_INTERFACE} rede_macvlan_manual")
    run_cmd(cmd_net)
    
    run_cmd(f"docker run -d --rm --name rec_server --network rede_macvlan_manual --ip {MACVLAN_SERVER_IP} {IMAGE_NAME}")

def setup_overlay():
    print("\n--- Configurando OVERLAY (Servidor) ---")
    run_cmd("docker rm -f rec_server", ignore_error=True)
    
    run_cmd("docker network create -d overlay --attachable rede_overlay_manual", ignore_error=True)
    
    run_cmd(f"docker run -d --rm --name rec_server --network rede_overlay_manual {IMAGE_NAME}")

def start_tools():
    print("... Aguardando container (3s) ...")
    time.sleep(3)
    print("... Iniciando Iperf3 e Netserver ...")
    run_cmd("docker exec -d rec_server iperf3 -s")
    run_cmd("docker exec -d rec_server netserver")
    print(f"\n[SUCESSO] Servidor rodando no modo: {sys.argv[1].upper()}")
    if sys.argv[1] == 'macvlan':
        print(f"-> IP Fixo: {MACVLAN_SERVER_IP}")
    else:
        print(f"-> Nome DNS: rec_server")

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ['macvlan', 'overlay']:
        print("Uso: python3 server_remote.py [macvlan | overlay]")
        sys.exit(1)
    
    mode = sys.argv[1]
    
    if mode == 'macvlan':
        setup_macvlan()
    else:
        setup_overlay()
        
    start_tools()