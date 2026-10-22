#!/usr/bin/env bash
# Records the machine/tool state that the handout's "measurement discipline"
# requirement asks for. Run before every experiment session:
#   scripts/env_capture.sh data/raw/env_$(date +%Y%m%d_%H%M%S).txt
out="${1:-/dev/stdout}"
PERF="${PERF:-$HOME/tools/perf/usr/bin/perf}"
export LD_LIBRARY_PATH="$HOME/tools/perf/usr/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

sec() { echo; echo "===== $1 ====="; }
{
  sec "date";            date -Is
  sec "host";            hostname
  sec "kernel";          uname -a
  sec "os-release";      cat /etc/os-release
  sec "lscpu";           lscpu
  sec "caches";          lscpu -C
  sec "cpu topology";    lscpu -e
  sec "governor (unique values across CPUs)"
  cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor | sort | uniq -c
  sec "scaling driver";  cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_driver
  sec "epp (unique)";    cat /sys/devices/system/cpu/cpu*/cpufreq/energy_performance_preference 2>/dev/null | sort | uniq -c
  sec "boost";           cat /sys/devices/system/cpu/cpufreq/boost 2>/dev/null || echo "n/a"
  sec "SMT";             cat /sys/devices/system/cpu/smt/control 2>/dev/null
  sec "THP enabled";     cat /sys/kernel/mm/transparent_hugepage/enabled
  sec "THP defrag";      cat /sys/kernel/mm/transparent_hugepage/defrag
  sec "perf_event_paranoid"; cat /proc/sys/kernel/perf_event_paranoid
  sec "memory";          free -h
  sec "numa";            numactl --hardware 2>/dev/null
  sec "load / users";    uptime; who
  sec "gcc";             gcc --version | head -1
  sec "perf";            "$PERF" --version 2>&1
} > "$out" 2>&1
[ "$out" != /dev/stdout ] && echo "environment saved to $out"
