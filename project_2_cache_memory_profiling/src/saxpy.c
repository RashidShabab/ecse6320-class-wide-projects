// saxpy.c - cache-miss impact on a lightweight kernel: y[i] = a * x[i] + y[i]
// ECSE 4320/6320 Project 2: Cache & Memory Performance Profiling
//
// Two float arrays x and y (total footprint = -s). Sweeping the footprint from
// L1-sized to DRAM-sized changes where the data comes from, and therefore the
// miss rate, while the arithmetic stays identical. Hardware counters (read
// in-process around the timed loop only) give misses per element, so runtime
// can be correlated with miss rate.
//
//   -p seq   y[i] = a*x[i] + y[i] in order (vectorized, prefetch-friendly)
//   -p rand  y[j] = a*x[j] + y[j] with j = idx[i], a shuffled permutation
//            (same work, but every element is a likely cache miss)
//
// Correctness: one pass is checked against a scalar reference before timing.
// Build:  gcc -O3 -march=native -Wall -Wextra -o saxpy src/saxpy.c

#define _GNU_SOURCE
#include <errno.h>
#include <getopt.h>
#include <linux/perf_event.h>
#include <math.h>
#include <sched.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>

#define HUGE_2M (2UL * 1024 * 1024)

static double now_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec * 1e9 + (double)ts.tv_nsec;
}

static uint64_t parse_size(const char *s) {
    char *end;
    double v = strtod(s, &end);
    switch (*end) {
        case 'k': case 'K': v *= 1024.0; break;
        case 'm': case 'M': v *= 1024.0 * 1024; break;
        case 'g': case 'G': v *= 1024.0 * 1024 * 1024; break;
        case '\0': break;
        default: fprintf(stderr, "bad size suffix in '%s'\n", s); exit(1);
    }
    return (uint64_t)v;
}

// ---- counters: cycles, instructions, L1D read misses, generic cache-misses, dTLB read misses ----
// PERF_COUNT_HW_CACHE_MISSES is mapped by Linux to an L2-miss event on AMD Zen, so the
// llc_miss_per_elem column counts L2 misses on this machine (name kept for data compatibility).
#define NCTR 5
static int fd[NCTR] = {-1, -1, -1, -1, -1};
static const char *cname[NCTR] = {"cycles", "instructions", "L1D read misses", "cache-misses (L2 on AMD)", "dTLB read misses"};
static void counters_open(void) {
    uint64_t miss = (uint64_t)PERF_COUNT_HW_CACHE_OP_READ << 8 | (uint64_t)PERF_COUNT_HW_CACHE_RESULT_MISS << 16;
    uint32_t type[NCTR] = {PERF_TYPE_HARDWARE, PERF_TYPE_HARDWARE, PERF_TYPE_HW_CACHE, PERF_TYPE_HARDWARE,
                           PERF_TYPE_HW_CACHE};
    uint64_t cfg[NCTR] = {PERF_COUNT_HW_CPU_CYCLES, PERF_COUNT_HW_INSTRUCTIONS, PERF_COUNT_HW_CACHE_L1D | miss,
                          PERF_COUNT_HW_CACHE_MISSES, PERF_COUNT_HW_CACHE_DTLB | miss};
    for (int i = 0; i < NCTR; i++) {
        struct perf_event_attr pe;
        memset(&pe, 0, sizeof pe);
        pe.type = type[i]; pe.size = sizeof pe; pe.config = cfg[i];
        pe.disabled = 1; pe.exclude_kernel = 1; pe.exclude_hv = 1;
        fd[i] = (int)syscall(__NR_perf_event_open, &pe, 0, -1, -1, 0);
        if (fd[i] < 0)
            fprintf(stderr, "# warning: counter '%s' unavailable (%s); reported as NaN\n", cname[i], strerror(errno));
    }
}
static void counters_start(void) {
    for (int i = 0; i < NCTR; i++)
        if (fd[i] >= 0) { ioctl(fd[i], PERF_EVENT_IOC_RESET, 0); ioctl(fd[i], PERF_EVENT_IOC_ENABLE, 0); }
}
static void counters_stop(double *v) {
    for (int i = 0; i < NCTR; i++) {
        v[i] = 0.0 / 0.0;
        if (fd[i] < 0) continue;
        ioctl(fd[i], PERF_EVENT_IOC_DISABLE, 0);
        uint64_t c = 0;
        if (read(fd[i], &c, sizeof c) == sizeof c) v[i] = (double)c;
    }
}

// ---- kernels (noinline so each is one clean, separately compiled loop) ----
__attribute__((noinline)) static void saxpy_seq(float a, const float *restrict x, float *restrict y, uint64_t n) {
    for (uint64_t i = 0; i < n; i++) y[i] = a * x[i] + y[i];
}
__attribute__((noinline)) static void saxpy_rand(float a, const float *restrict x, float *restrict y,
                                                  const uint32_t *restrict idx, uint64_t n) {
    for (uint64_t i = 0; i < n; i++) { uint32_t j = idx[i]; y[j] = a * x[j] + y[j]; }
}

static void *alloc(uint64_t bytes, const char *pages) {
    uint64_t len = (bytes + HUGE_2M - 1) & ~(HUGE_2M - 1);
    char *raw = mmap(NULL, len + HUGE_2M, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (raw == MAP_FAILED) { perror("mmap"); exit(1); }
    char *p = (char *)(((uintptr_t)raw + HUGE_2M - 1) & ~(HUGE_2M - 1));
    if (strcmp(pages, "4k") == 0) madvise(p, len, MADV_NOHUGEPAGE);
    else if (strcmp(pages, "huge") == 0) madvise(p, len, MADV_HUGEPAGE);
    memset(p, 0, len);
    return p;
}

static void usage(const char *prog) {
    fprintf(stderr,
        "usage: %s -s SIZE [options]\n"
        "  -s SIZE     footprint of x + y together, e.g. 32K, 1M, 1G (required)\n"
        "  -p PATTERN  seq | rand (default seq)\n"
        "  -P PAGES    thp | 4k | huge (default huge)\n"
        "  -c CPU      pin to this CPU (default 2)\n"
        "  -r REPS     timed repetitions (default 5)\n"
        "  -n N        elements processed per repetition (default max(2 * elements, 64M))\n"
        "  -H          print CSV header line\n", prog);
    exit(1);
}

int main(int argc, char **argv) {
    uint64_t size = 0, n_target = 0;
    const char *pattern = "seq", *pages = "huge";
    int cpu = 2, reps = 5, header = 0, opt;
    while ((opt = getopt(argc, argv, "s:p:P:c:r:n:H")) != -1) {
        switch (opt) {
            case 's': size = parse_size(optarg); break;
            case 'p': pattern = optarg; break;
            case 'P': pages = optarg; break;
            case 'c': cpu = atoi(optarg); break;
            case 'r': reps = atoi(optarg); break;
            case 'n': n_target = parse_size(optarg); break;
            case 'H': header = 1; break;
            default: usage(argv[0]);
        }
    }
    if (header)
        printf("size_bytes,pattern,pages,cpu,rep,elements,ns_per_elem,cycles_per_elem,ipc,eff_ghz,"
               "gflops,gb_per_s,l1d_miss_per_elem,llc_miss_per_elem,dtlb_miss_per_elem\n");
    if (size == 0) { if (header) return 0; usage(argv[0]); }
    int is_rand = strcmp(pattern, "rand") == 0;
    if ((!is_rand && strcmp(pattern, "seq")) || (strcmp(pages, "4k") && strcmp(pages, "huge") && strcmp(pages, "thp")))
        usage(argv[0]);

    uint64_t n = size / (2 * sizeof(float));  // elements per array
    if (n < 64 || n > 0xFFFFFFFFULL) { fprintf(stderr, "size out of range\n"); return 1; }
    if (cpu >= 0) {
        cpu_set_t set; CPU_ZERO(&set); CPU_SET(cpu, &set);
        if (sched_setaffinity(0, sizeof set, &set)) { perror("sched_setaffinity"); return 1; }
    }
    float *x = alloc(n * sizeof(float), pages), *y = alloc(n * sizeof(float), pages);
    uint32_t *idx = NULL;
    if (is_rand) {
        idx = alloc(n * sizeof(uint32_t), pages);
        uint64_t s = 0x9E3779B97F4A7C15ULL;
        for (uint64_t i = 0; i < n; i++) idx[i] = (uint32_t)i;
        for (uint64_t i = n - 1; i > 0; i--) {
            s ^= s << 13; s ^= s >> 7; s ^= s << 17;
            uint64_t j = s % (i + 1);
            uint32_t t = idx[i]; idx[i] = idx[j]; idx[j] = t;
        }
    }
    for (uint64_t i = 0; i < n; i++) { x[i] = (float)(i % 1000) * 0.001f; y[i] = 1.0f; }
    const float a = 0.5f;

    // ---- validation: one kernel pass vs a scalar double-precision reference ----
    uint64_t chk = n < 4096 ? n : 4096;
    float *y0 = malloc(chk * sizeof(float));
    memcpy(y0, y, chk * sizeof(float));
    if (is_rand) saxpy_rand(a, x, y, idx, n); else saxpy_seq(a, x, y, n);
    for (uint64_t i = 0; i < chk; i++) {
        double ref = (double)a * x[i] + y0[i];
        if (fabs(y[i] - ref) > 1e-5 * fabs(ref) + 1e-6) {
            fprintf(stderr, "VALIDATION FAILED at %lu: %g vs %g\n", (unsigned long)i, (double)y[i], ref);
            return 2;
        }
    }
    free(y0);
    for (uint64_t i = 0; i < n; i++) y[i] = 1.0f;  // reset

    uint64_t passes = n_target ? (n_target + n - 1) / n : 0;
    if (!passes) { uint64_t want = (2 * n > (64ULL << 20)) ? 2 * n : (64ULL << 20); passes = (want + n - 1) / n; }
    uint64_t elems = passes * n;
    fprintf(stderr, "# size=%lu elements=%lu pattern=%s pages=%s cpu=%d passes=%lu validation=ok\n",
            (unsigned long)size, (unsigned long)n, pattern, pages, cpu, (unsigned long)passes);

    counters_open();
    for (int w = 0; w < 2; w++) { if (is_rand) saxpy_rand(a, x, y, idx, n); else saxpy_seq(a, x, y, n); }  // warm-up

    volatile float sink = 0;
    for (int r = 0; r < reps; r++) {
        double c[NCTR];
        counters_start();
        double t0 = now_ns();
        for (uint64_t p = 0; p < passes; p++) {
            if (is_rand) saxpy_rand(a, x, y, idx, n); else saxpy_seq(a, x, y, n);
        }
        double t1 = now_ns();
        counters_stop(c);
        sink += y[r % n];
        double ns = (t1 - t0) / (double)elems;
        // 12 B per element: read x, read y, write y (index array not counted)
        printf("%lu,%s,%s,%d,%d,%lu,%.4f,%.3f,%.3f,%.3f,%.3f,%.3f,%.4f,%.4f,%.4f\n",
               (unsigned long)size, pattern, pages, cpu, r, (unsigned long)elems, ns, c[0] / elems,
               c[1] / c[0], c[0] / (t1 - t0), 2.0 / ns, 12.0 / ns, c[2] / elems, c[3] / elems, c[4] / elems);
        fflush(stdout);
    }
    (void)sink;
    return 0;
}
