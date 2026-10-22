// bwbench.c - memory bandwidth benchmark (stride, pattern, read/write mix, threads)
// ECSE 6320 Project 2: Cache & Memory Performance Profiling
//
// Unlike pchase, the accesses here are INDEPENDENT: the address of access i+1
// does not depend on the data of access i. The CPU can therefore keep many
// misses in flight at once, so the result is throughput (GB/s), not latency.
//
// Unit of work = one 64-byte cache line ("chunk"). `stride` is the distance
// between the starts of consecutive chunks:
//   stride 64   -> chunks touch each other: every byte of every line is used
//   stride 256  -> 1 line used, 3 lines skipped
//   stride 1024 -> 1 line used, 15 lines skipped
// Reads sum the 8 words of a line; writes store 8 words into it.
// Read/write mix: -m R = percent of chunks that are reads (100, 70, 50, 0 ...).
//
// Reported GB/s = bytes of the chunks touched / time. For writes the real DRAM
// traffic is about 2x that: a normal store first READS the line into the cache
// ("read for ownership") and later writes it back.
//
// Build:  gcc -O3 -march=native -pthread -Wall -Wextra -o bwbench src/bwbench.c

#define _GNU_SOURCE
#include <getopt.h>
#include <pthread.h>
#include <sched.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>

#define LINE 64
#define WORDS (LINE / 8)
#define HUGE_2M (2UL * 1024 * 1024)
#define MAX_THREADS 64

static double now_s(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
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

// Parses a CPU list like "2-7,0,1,8-15" into cpus[]; returns the count.
static int parse_cpus(const char *s, int *cpus, int max) {
    int n = 0;
    char *copy = strdup(s), *save = NULL;
    for (char *tok = strtok_r(copy, ",", &save); tok && n < max; tok = strtok_r(NULL, ",", &save)) {
        int a, b;
        if (sscanf(tok, "%d-%d", &a, &b) == 2) {
            for (int c = a; c <= b && n < max; c++) cpus[n++] = c;
        } else {
            cpus[n++] = atoi(tok);
        }
    }
    free(copy);
    return n;
}

typedef struct {
    int id, cpu;
    char *base;           // this thread's private region
    uint64_t chunks;      // chunks per pass
    uint64_t stride;
    uint32_t *order;      // chunk visiting order (random pattern only)
    int read_pct;
    uint64_t passes;
    const char *pages;
    uint64_t region_len;
    pthread_barrier_t *start, *done;
    int reps;
    uint64_t sink;
} worker_t;

// One pass over the region. `order` == NULL means sequential.
static uint64_t run_pass(char *base, uint64_t chunks, uint64_t stride,
                         const uint32_t *order, int read_pct, uint64_t pass) {
    uint64_t acc0 = 0, acc1 = 0;
    int bres = 0;  // Bresenham counter: spreads reads evenly, e.g. 70% -> 7 of every 10
    for (uint64_t i = 0; i < chunks; i++) {
        uint64_t idx = order ? order[i] : i;
        uint64_t *p = (uint64_t *)(base + idx * stride);
        bres += read_pct;
        if (bres >= 100) {       // read the line
            bres -= 100;
            uint64_t s0 = p[0] + p[1] + p[2] + p[3];
            uint64_t s1 = p[4] + p[5] + p[6] + p[7];
            acc0 += s0; acc1 += s1;
        } else {                 // write the line
            uint64_t v = pass + i;
            for (int w = 0; w < WORDS; w++) p[w] = v;
        }
    }
    return acc0 ^ acc1;
}

static void *worker(void *arg) {
    worker_t *w = arg;
    cpu_set_t set; CPU_ZERO(&set); CPU_SET(w->cpu, &set);
    if (pthread_setaffinity_np(pthread_self(), sizeof set, &set) != 0)
        fprintf(stderr, "# warning: could not pin thread %d to CPU %d\n", w->id, w->cpu);

    // Page policy and first touch happen inside the pinned thread.
    if (strcmp(w->pages, "4k") == 0) madvise(w->base, w->region_len, MADV_NOHUGEPAGE);
    else if (strcmp(w->pages, "huge") == 0) madvise(w->base, w->region_len, MADV_HUGEPAGE);
    memset(w->base, 1, w->region_len);

    uint64_t sink = 0;
    run_pass(w->base, w->chunks, w->stride, w->order, w->read_pct, 0);  // warm-up pass
    for (int r = 0; r < w->reps; r++) {
        pthread_barrier_wait(w->start);              // everyone starts together
        for (uint64_t p = 0; p < w->passes; p++)
            sink += run_pass(w->base, w->chunks, w->stride, w->order, w->read_pct, p);
        pthread_barrier_wait(w->done);               // main stops the clock after all finish
    }
    w->sink = sink;
    return NULL;
}

static void usage(const char *prog) {
    fprintf(stderr,
        "usage: %s -s SIZE [options]\n"
        "  -s SIZE     total working set across all threads, e.g. 32K, 16M, 1G (required)\n"
        "  -S BYTES    stride between 64 B chunks: 64, 128, 256, 1024 ... (default 64)\n"
        "  -p PATTERN  seq | rand (default seq)\n"
        "  -m READPCT  percent of chunks that are reads: 100, 70, 50, 0 (default 100)\n"
        "  -t THREADS  number of threads (default 1)\n"
        "  -c CPUS     CPU list threads are pinned to, in order (default 2-7,0,1,8-15)\n"
        "  -P PAGES    thp | 4k | huge (default huge)\n"
        "  -r REPS     timed repetitions (default 5)\n"
        "  -b BYTES    bytes touched per repetition, all threads (default 4G)\n"
        "  -x SEED     RNG seed for the random pattern\n"
        "  -H          print CSV header line\n", prog);
    exit(1);
}

int main(int argc, char **argv) {
    uint64_t size = 0, stride = 64, target = 4ULL << 30, seed = 0x9E3779B97F4A7C15ULL;
    const char *pattern = "seq", *pages = "huge", *cpulist = "2-7,0,1,8-15";
    int read_pct = 100, nthreads = 1, reps = 5, header = 0, opt;

    while ((opt = getopt(argc, argv, "s:S:p:m:t:c:P:r:b:x:H")) != -1) {
        switch (opt) {
            case 's': size = parse_size(optarg); break;
            case 'S': stride = parse_size(optarg); break;
            case 'p': pattern = optarg; break;
            case 'm': read_pct = atoi(optarg); break;
            case 't': nthreads = atoi(optarg); break;
            case 'c': cpulist = optarg; break;
            case 'P': pages = optarg; break;
            case 'r': reps = atoi(optarg); break;
            case 'b': target = parse_size(optarg); break;
            case 'x': seed = strtoull(optarg, NULL, 0) | 1; break;
            case 'H': header = 1; break;
            default: usage(argv[0]);
        }
    }
    if (header)
        printf("size_bytes,threads,stride,pattern,read_pct,pages,rep,bytes,seconds,gb_per_s,cpus\n");
    if (size == 0) { if (header) return 0; usage(argv[0]); }

    int is_rand = strcmp(pattern, "rand") == 0;
    if ((!is_rand && strcmp(pattern, "seq") != 0) || stride < LINE || stride % LINE ||
        read_pct < 0 || read_pct > 100 || nthreads < 1 || nthreads > MAX_THREADS ||
        (strcmp(pages, "4k") && strcmp(pages, "huge") && strcmp(pages, "thp")))
        usage(argv[0]);

    int cpus[MAX_THREADS];
    int ncpus = parse_cpus(cpulist, cpus, MAX_THREADS);
    if (ncpus < nthreads) { fprintf(stderr, "CPU list has %d CPUs, need %d\n", ncpus, nthreads); return 1; }

    // Each thread gets its own 2 MiB-aligned region (no sharing between threads).
    uint64_t per = size / (uint64_t)nthreads;
    uint64_t chunks = per / stride;
    if (chunks < 1 || chunks > 0xFFFFFFFFULL) { fprintf(stderr, "size/stride/threads invalid\n"); return 1; }
    uint64_t region_len = ((chunks * stride) + HUGE_2M - 1) & ~(HUGE_2M - 1);
    char *raw = mmap(NULL, region_len * nthreads + HUGE_2M, PROT_READ | PROT_WRITE,
                     MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (raw == MAP_FAILED) { perror("mmap"); return 1; }
    char *buf = (char *)(((uintptr_t)raw + HUGE_2M - 1) & ~(HUGE_2M - 1));

    uint64_t bytes_per_pass = chunks * LINE * (uint64_t)nthreads;
    uint64_t passes = (target + bytes_per_pass - 1) / bytes_per_pass;
    if (passes < 1) passes = 1;

    pthread_barrier_t start, done;
    pthread_barrier_init(&start, NULL, nthreads + 1);
    pthread_barrier_init(&done, NULL, nthreads + 1);

    worker_t w[MAX_THREADS];
    pthread_t th[MAX_THREADS];
    for (int t = 0; t < nthreads; t++) {
        uint32_t *order = NULL;
        if (is_rand) {  // Fisher-Yates shuffle of chunk indices, different per thread
            order = malloc(chunks * sizeof *order);
            if (!order) { perror("malloc"); return 1; }
            for (uint64_t i = 0; i < chunks; i++) order[i] = (uint32_t)i;
            uint64_t x = seed + (uint64_t)t * 0x632BE59BD9B4E019ULL;
            for (uint64_t i = chunks - 1; i > 0; i--) {
                x ^= x << 13; x ^= x >> 7; x ^= x << 17;
                uint64_t j = x % (i + 1);
                uint32_t tmp = order[i]; order[i] = order[j]; order[j] = tmp;
            }
        }
        w[t] = (worker_t){ .id = t, .cpu = cpus[t], .base = buf + (uint64_t)t * region_len,
                           .chunks = chunks, .stride = stride, .order = order,
                           .read_pct = read_pct, .passes = passes, .pages = pages,
                           .region_len = region_len, .start = &start, .done = &done, .reps = reps };
        pthread_create(&th[t], NULL, worker, &w[t]);
    }

    char cpustr[512] = "";
    for (int t = 0; t < nthreads; t++) {
        char b[16];
        snprintf(b, sizeof b, t ? " %d" : "%d", cpus[t]);
        strncat(cpustr, b, sizeof cpustr - strlen(cpustr) - 1);
    }
    fprintf(stderr, "# size=%lu threads=%d per_thread=%lu stride=%lu chunks=%lu pattern=%s read_pct=%d "
            "pages=%s passes=%lu cpus=[%s]\n", (unsigned long)size, nthreads, (unsigned long)per,
            (unsigned long)stride, (unsigned long)chunks, pattern, read_pct, pages,
            (unsigned long)passes, cpustr);

    uint64_t bytes = bytes_per_pass * passes;
    for (int r = 0; r < reps; r++) {
        pthread_barrier_wait(&start);
        double t0 = now_s();
        pthread_barrier_wait(&done);
        double t1 = now_s();
        double sec = t1 - t0;
        printf("%lu,%d,%lu,%s,%d,%s,%d,%lu,%.6f,%.3f,%s\n", (unsigned long)size, nthreads,
               (unsigned long)stride, pattern, read_pct, pages, r, (unsigned long)bytes, sec,
               (double)bytes / sec / 1e9, cpustr);
        fflush(stdout);
    }
    uint64_t sink = 0;
    for (int t = 0; t < nthreads; t++) { pthread_join(th[t], NULL); sink ^= w[t].sink; free(w[t].order); }
    if (sink == 42) fprintf(stderr, "#\n");  // keeps the reads from being optimized away
    munmap(raw, region_len * nthreads + HUGE_2M);
    return 0;
}
