# Caracterização e Avaliação de Métodos de Comunicação em Contêineres Docker

Este repositório contém o código-fonte, scripts de automação e dados brutos utilizados no trabalho de avaliação de desempenho de redes Docker, desenvolvido para a disciplina de **Redes de Computadores** do curso de Ciência da Computação da **Universidade do Estado de Santa Catarina (UDESC)**.

**Autores:**
*   Arthur Lodetti Gonçalves
*   Gustavo de Souza
*   José Augusto Laube

---

## Objetivo

O objetivo deste projeto é caracterizar e avaliar comparativamente o desempenho dos diferentes drivers de rede do Docker (**Bridge, Host, Macvlan/IPVlan e Overlay**) em dois cenários distintos:
1.  **Intra-Host:** Comunicação entre contêineres na mesma máquina física.
2.  **Inter-Host:** Comunicação entre contêineres em máquinas físicas distintas conectadas via LAN.

As métricas analisadas incluem **Vazão (Throughput)**, **Latência**, **Jitter**, **Perda de Pacotes** e **Eficiência de CPU**.

---

## Estrutura do Projeto

*   `Dockerfile`: Definição da imagem padronizada contendo as ferramentas de teste (`iperf3` e `netperf`).
*   `benchmark_host_bridge.py`: Script de automação completo para rodar os testes locais (Cenário Intra-Host).
*   `server_remote_mac_over.py`: Script para configurar o nó **Servidor** nos testes distribuídos (Cenário Inter-Host).
*   `client_analyst_mac_over.py`: Script para configurar o nó **Cliente** nos testes distribuídos, executar as medições e gerar gráficos.
*   `RESULTADOS_HOST_BRIDGE/`: Contém os gráficos e CSVs gerados pelos testes locais.
*   `RESULTADOS_MULTI_HOST_2MAQUINAS.../`: Contém os resultados dos testes distribuídos.

---
