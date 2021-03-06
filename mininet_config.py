#!/usr/bin/python
import argparse
import os
import random
import re
import time
import statistics

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.link import TCLink
from mininet.log import setLogLevel
from mininet.clean import Cleanup


class GEANTopo(Topo):
    "GEANT topology for traffic matrix"

    def __init__(self, bw: float, delay: str):
        # Initialize topology and default options
        Topo.__init__(self)

        # add nodes, switches first...
        switch_1 = self.addSwitch('s1')
        switch_2 = self.addSwitch('s2')

        # ... and now hosts
        host_1 = self.addHost('h1')
        host_2 = self.addHost('h2')

        # add edges between switch and corresponding host
        self.addLink(switch_1, host_1)
        self.addLink(switch_2, host_2)

        # add edges between switches
        self.addLink(switch_1, switch_2, bw=bw,
                     delay=delay, max_queue_size=1000)


topos = {'geant': GEANTopo}


def launch(exec_id: str, mininet_bw: float, mininet_delay: str, server_queue: str, server_push: int, client_dash: str,
           exec_duration: int, load: float, out_folder: str):
    """
    Create and launch the network
    """
    # Create network
    print("*** Creating Network ***\n")
    Cleanup()
    topog = GEANTopo(mininet_bw, mininet_delay)
    net = Mininet(topo=topog, link=TCLink)

    # Run network
    print("*** Firing up Mininet ***\n")
    net.start()
    hosts = net.hosts

    server = hosts[0]
    client = hosts[1]

    # ******************************
    # Rodando servidor iPerf

    print("\n*** Running iPerf server: "+server.IP()+" ***")
    iperf_port = "5002"
    iperf_server_command = "iperf3 -s -p " + iperf_port + " > out/" + out_folder + "/" \
                           + exec_id + "-iperf_server_out.txt &"
    print(iperf_server_command)
    server.cmd(iperf_server_command)
    iperf_server_pid = get_last_pid(server)
    print("-> iPerf server running on process: ", iperf_server_pid)

    # ******************************
    # Rodando servidor de v??deo

    print("\n*** Running server: "+server.IP()+" ***")
    server.cmd("export PYTHONPATH=$PYTHONPATH:/root/tcc")

    push_flag = ""
    if server_push:
        push_flag = "-p"

    server_command = "python3 src/server.py -c cert/ssl_cert.pem -k cert/ssl_key.pem -q " + server_queue + " " \
                     + push_flag + " > out/" + out_folder + "/" + exec_id + "-server_out.txt &"
    print(server_command)
    server.cmd(server_command)
    server_pid = get_last_pid(server)
    print("-> Server running on process: ", server_pid)

    # ******************************
    # Rodando cliente do iPerf
    print("\n*** Running iPerf client for " + str(load) + " load ***")
    out_file = "out/" + out_folder + "/" + exec_id + "-iperf_client_out.txt"
    iperf_params = " ".join(["-ip " + server.IP(), "-p " + iperf_port, "-mb " + str(mininet_bw), "-l " + str(load),
                             "-o " + out_file])
    iperf_command = "python3 iperf_client_exec.py "+iperf_params+" &"
    print(iperf_command)
    client.cmd(iperf_command)
    iperf_client_pid = get_last_pid(client)
    print("-> iPerf client running on process: ", iperf_client_pid)

    # ******************************
    # Rodando cliente de v??deo

    print("\n*** Running client: "+client.IP()+" ***")
    client.cmd("export PYTHONPATH=$PYTHONPATH:/root/tcc")
    client_command = "python3 src/client.py -c cert/pycacert.pem "+server.IP()+":4433 -i data/user_input.csv -da " \
                     + client_dash + " > out/" + out_folder + "/" + exec_id + "-client_out.txt &"
    print(client_command)
    client.cmd(client_command)
    client_pid = get_last_pid(client)
    print("-> Client running on process: ", client_pid)
    time.sleep(2)

    # ******************************
    # Medida de tr??fego inicial

    backbone = net.linksBetween(net.get('s1'), net.get('s2'))[0]

    # get initial rates
    init_rx, init_tx = get_rx_tx(backbone.intf1.ifconfig())

    # get initial time
    initial_timestamp = time.time()
    print("\n*** Transmiss??o inicial ***")
    print("RX Inicial: " + str(init_rx) + "bits")
    print("TX Inicial: " + str(init_tx) + "bits")

    # ******************************
    # Aguardando fim

    print("\n*** Checking for client closure ***")

    is_running = True
    while is_running:
        process_command = "ps | grep " + client_pid
        process = client.cmd(process_command)
        if len(process) == 0:
            is_running = False
        else:
            time.sleep(2)

    print("\n\nCLIENT FINISHED\n\n")

    # ******************************
    # Medida de tr??fego final

    # get final rates
    final_rx, final_tx = get_rx_tx(backbone.intf1.ifconfig())

    # get final time
    closure_timestamp = time.time()

    print("\n*** Transmiss??o final ***")
    print("RX Final: " + str(final_rx) + "bits")
    print("TX Final: " + str(final_tx) + "bits")

    # ******************************
    # C??lculo de uso do canal

    print("*** Utiliza????o do Canal ***\n")

    total_rx = final_rx - init_rx
    total_tx = final_tx - init_tx

    execution_time = closure_timestamp - initial_timestamp
    throughput = (total_rx + total_tx) / execution_time

    print("Taxa no canal: " + str(throughput) + "bits/s")
    print("Capacidade do link: " + str(mininet_bw) + "Mbps")

    channel_usage = throughput/(1048576*mininet_bw)
    print("Uso do canal: " + str(channel_usage))

    # ******************************
    # Encerrando processos

    print("\n*** Killing remaining process ***\n")
    print("> Killing video server\n")
    server.cmd("kill -9 "+server_pid)
    print("> Killing iPerf server\n")
    server.cmd("kill -9 "+iperf_server_pid)
    print("> Killing iPerf client\n\n")
    client.cmd("kill -9 "+iperf_client_pid)
    print("*** Stopping Mininet ***")
    net.stop()


def get_last_pid(host):
    pid = host.cmd("echo $!")
    result = re.findall(r'\d+', pid)
    return result[0]


def get_rx_tx(ifconfig):
    rx_regex = re.compile(r"RX packets \d+  bytes (\d+)")
    tx_regex = re.compile(r"TX packets \d+  bytes (\d+)")

    # extract RX
    rx = rx_regex.search(ifconfig, re.MULTILINE).group(1)

    # extract TX
    tx = tx_regex.search(ifconfig, re.MULTILINE).group(1)

    # return values in bits
    return int(rx) * 8, int(tx) * 8


def get_random_iperf_params(on_avg, off_avg):
    def warmup(a, b, size=100000):
        samples = []
        for i in range(size):
            c = random.uniform(a, b)
            samples.append(c)

        return samples

    # Encontra slices de tamanho slice_size na lista
    # samples que tem media igual a
    # m??dia desejada (avg)
    def trail(a=0, b=2, avg=10, size=1000000, slice_size=5, slice_count=3):
        random_lists = []
        samples = warmup(a, b, size)
        for i in range(int(size / slice_size)):
            picked = [int(x * avg)
                      for x in samples[slice_size * i:(i + 1) * slice_size]]
            if (statistics.mean(picked) == avg) and (slice_count > 0):
                random_lists.append(picked)
                slice_count -= 1
        return random_lists

    on_list = trail(avg=on_avg)
    off_list = trail(avg=off_avg)

    i_on = random.randint(0, len(on_list))
    i_off = random.randint(0, len(off_list))

    return i_on, i_off


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Mininet configuration and execution script")

    # Id
    parser.add_argument(
        "-id",
        type=str,
        default="",
        help="The identifier of the execution for logging purposes"
    )

    # Mininet parameters
    parser.add_argument(
        "-mb",
        "--mn-bandwidth",
        type=float,
        default=100.00,
        help="The channel bandwidth (float) of the mininet link in Mbps. Ex: '100.00'"
    )
    parser.add_argument(
        "-md",
        "--mn-delay",
        type=str,
        default="1ms",
        help="The channel delay of the mininet link. Ex: '1ms'"
    )

    # Server Parameters
    parser.add_argument(
        "-sq",
        "--server-queue",
        type=str,
        choices=['WFQ', 'SP', 'FIFO'],
        default="FIFO",
        help="The queuing algorithm used by the Video Server (WFQ, FIFO or SP)"
    )
    parser.add_argument(
        "-sp",
        "--server-push",
        type=int,
        choices=[0, 1],
        default=1,
        help="If server push is enabled or not"
    )

    # Client Parameters
    parser.add_argument(
        "-da",
        "--dash-algorithm",
        required=False,
        choices=['basic', 'basic2'],
        default="basic",
        type=str,
        help="dash algorithm (options: basic, basic2) - (defaults to basic)",
    )
    parser.add_argument(
        "-d",
        "--exec-duration",
        type=int,
        default=80,
        help="The duration of the background traffic on iPerf in seconds"
    )
    parser.add_argument(
        "-l",
        "--load",
        type=float,
        default=0,
        help="The bandwidth consumption by the background traffic on iPerf. Ex: 0.1 = 10%"
    )
    parser.add_argument(
        "-out",
        "--out-directory",
        type=str,
        default="default",
        help="The folder to store the scripts outputs"
    )
    args = parser.parse_args()

    # Cleaning up mininet
    os.system("sudo mn -c")
    # Tell mininet to print useful information
    setLogLevel('info')

    launch(exec_id=args.id, mininet_bw=args.mn_bandwidth, mininet_delay=args.mn_delay,
           server_queue=args.server_queue, server_push=args.server_push, client_dash=args.dash_algorithm,
           exec_duration=args.exec_duration, load=args.load, out_folder=args.out_directory)
