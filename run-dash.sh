#!/bin/bash

# -mb > --mn-bandwidth: Bandwidth of mininet link
# -md > --mn-delay: Delay of mininet link
# -sq > --server-queue: Queuing on video Server
# -sp > --server-push: Is push enabled
# -da > --dash-algorithm: Dash algorithm
# -bd > --bg-duration: Duration of iperf background traffic (repeated)
# -bt > --bg-traffic: Bandwidth of iperf background traffic
# -pd > --peek-duration: Duration of iperf peek traffic (repeated)
# -pt > --peek-traffic: Bandwidth of iperf peek traffic

# printf "================ Execução de Simulação com alternância nos algoritmos dash ================\n\n"

# START="$1"
# push=1 # Push sempre ativado
# bg_d=80 #sec
# queue="WFQ" # Queue sempre WFQ

# id=1
# loads=(0.1 0.3)
# bands=(10.00 8.00) #Mbps
# delays=("5ms" "50ms" "75ms" "100ms" "125ms" "150ms")
# dashes=("basic" "basic2")

# timestamp="date +%s"
# exec_folder=$(eval "$timestamp")
# mkdir out/"${exec_folder}"

# for load in "${loads[@]}"; do
#   for bw in "${bands[@]}"; do
#     for delay in "${delays[@]}"; do
#       for dash in "${dashes[@]}"; do
#         if [[ $id -ge $START ]]; then
#           printf "*** Cenário %d ***\n" "$id"

#           printf "BW: %f, Delay: %s, Queuing: %s, Push: %d" "$bw" "$delay" "$queue" "$push"
#           printf ", Dash: %s, BG Traffic: %f\n" "$dash" "$load"

#           for ((i = 0 ; i < 5 ; i++)); do
#             printf "Exec %d\n" "$i"
#             date
#             exec_id="${id}-${i}"
#             python3 mininet_config.py -id "${exec_id}" -mb "${bw}" -md "${delay}" -sq "${queue}" -sp ${push} -da ${dash} -d ${bg_d} -l "${load}" -out "${exec_folder}" > out/"${exec_folder}"/${exec_id}-exec.txt 2>&1
#             rm -rf data/client_files_*
#           done
#         fi

#         ((++id))
#       done
#     done
#   done
# done


START="$1"
push=1 # Push sempre ativado
bg_d=80 #sec
queue="WFQ" # Queue sempre WFQ

id=1
loads=(0.1)
bands=(10.00) #Mbps
delays=("5ms")
dashes=("basic")

timestamp="date +%s"
exec_folder=$(eval "$timestamp")
mkdir out/"${exec_folder}"

for load in "${loads[@]}"; do
  for bw in "${bands[@]}"; do
    for delay in "${delays[@]}"; do
      for dash in "${dashes[@]}"; do
        if [[ $id -ge $START ]]; then
          printf "*** Cenário %d ***\n" "$id"

          printf "BW: %f, Delay: %s, Queuing: %s, Push: %d" "$bw" "$delay" "$queue" "$push"
          printf ", Dash: %s, BG Traffic: %f\n" "$dash" "$load"

          for ((i = 0 ; i < 5 ; i++)); do
            printf "Exec %d\n" "$i"
            date
            exec_id="${id}-${i}"
            python3 mininet_config.py -id "${exec_id}" -mb "${bw}" -md "${delay}" -sq "${queue}" -sp ${push} -da ${dash} -d ${bg_d} -l "${load}" -out "${exec_folder}" > out/"${exec_folder}"/${exec_id}-exec.txt 2>&1
            rm -rf data/client_files_*
          done
        fi

        ((++id))
      done
    done
  done
done
