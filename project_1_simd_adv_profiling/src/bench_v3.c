#define _GNU_SOURCE
#include "kernels_v3.h"
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
#include <math.h>
#include <time.h>
#include <unistd.h>
#include <sched.h>
#include <sys/syscall.h>
#include <sys/ioctl.h>
#include <linux/perf_event.h>
#include <x86intrin.h>

static volatile real sink;
static double now(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC_RAW, &t);
    return t.tv_sec + t.tv_nsec*1e-9;
}
static uint64_t ticks(void) {
    unsigned aux;
    _mm_lfence();
    uint64_t t = __rdtscp(&aux);
    _mm_lfence();
    return t;
}
static size_t number(const char *s) {
    char *end; errno = 0;
    unsigned long long v = strtoull(s, &end, 10);
    if (errno || *end || *s == '-' || !*s || v > SIZE_MAX) {
        fprintf(stderr, "invalid integer: %s\n", s); exit(2);
    }
    return (size_t)v;
}
static real initial_x(size_t i) { return (real)((int)(i%17)-8)/(real)16; }
static real initial_y(size_t i) { return (real)((int)(i%13)-6)/(real)16; }
static void invoke(int kind, real *x, real *y, size_t n, size_t stride) {
    if (kind == 0) saxpy_v3(x,y,n,stride);
    else if (kind == 1) sink = dot_v3(x,y,n);
    else if (kind == 2) stencil_v3(x,y,n);
    else copy_v3(x,y,n);
}
int main(int argc, char **argv) {
    if (argc != 8) {
        fprintf(stderr,"Usage: bench saxpy|dot|stencil|copy N INNER STRIDE OFFSET REPEATS CPU\n"); return 2;
    }
    int kind = !strcmp(argv[1],"saxpy") ? 0 : !strcmp(argv[1],"dot") ? 1 : !strcmp(argv[1],"stencil") ? 2 : !strcmp(argv[1],"copy") ? 3 : -1;
    size_t n=number(argv[2]), inner=number(argv[3]), stride=number(argv[4]);
    size_t offset=number(argv[5]), repeats=number(argv[6]), cpu=number(argv[7]);
    if (kind < 0 || !n || !inner || inner>50000 || !stride || stride>8 || offset>15 || repeats<2 || repeats>100 || (kind!=0 && stride!=1) || cpu>=CPU_SETSIZE) return 2;
    cpu_set_t affinity; CPU_ZERO(&affinity); CPU_SET(cpu,&affinity);
    if (sched_setaffinity(0,sizeof affinity,&affinity)) {perror("affinity"); return 2;}
    if (n > (SIZE_MAX/sizeof(real)-offset-18)/stride) return 2;
    size_t span=n*stride+2, count=span+offset+16;
    real *xb=NULL,*yb=NULL;
    if (posix_memalign((void**)&xb,64,count*sizeof(real)) || posix_memalign((void**)&yb,64,count*sizeof(real))) {free(xb); free(yb); return 2;}
    real *x=xb+offset,*y=yb+offset;
    for(size_t i=0;i<count;i++){xb[i]=(real)99;yb[i]=(real)99;}
    for(size_t i=0;i<span;i++) x[i]=initial_x(i);
    /* Actual unhalted core cycles if WSL exposes a PMU. Never relabel TSC ticks. */
    struct perf_event_attr attr={0};
    attr.size=sizeof attr; attr.type=PERF_TYPE_HARDWARE; attr.config=PERF_COUNT_HW_CPU_CYCLES;
    attr.disabled=1; attr.exclude_kernel=1; attr.exclude_hv=1;
    attr.read_format=PERF_FORMAT_TOTAL_TIME_ENABLED|PERF_FORMAT_TOTAL_TIME_RUNNING;
    int fd=(int)syscall(SYS_perf_event_open,&attr,0,-1,-1,0);
    int counter_errno=fd<0?errno:0;
    double seconds[100], tsc[100], cycles[100];
    double max_error=0; int guards_ok=1;
    for(int trial=-3;trial<(int)repeats;trial++) {
        for(size_t i=0;i<span;i++) y[i]=initial_y(i);
        if(fd>=0){ioctl(fd,PERF_EVENT_IOC_RESET,0);ioctl(fd,PERF_EVENT_IOC_ENABLE,0);}
        double start=now(); uint64_t t0=ticks();
        for(size_t j=0;j<inner;j++) invoke(kind,x,y,n,stride);
        uint64_t t1=ticks(); double end=now();
        struct {uint64_t value,enabled,running;} counter={0};
        int valid=0;
        if(fd>=0){ioctl(fd,PERF_EVENT_IOC_DISABLE,0);valid=read(fd,&counter,sizeof counter)==sizeof counter && counter.running>0;}
        if(trial>=0) {
            seconds[trial]=(end-start)/inner;
            tsc[trial]=(double)(t1-t0)/inner/n;
            cycles[trial]=valid?(double)counter.value*counter.enabled/counter.running/inner/n:-1;
        }
        /* Binary-fraction inputs keep this sanity check exact in both dtypes.
         * Validate EVERY interval and unchanged gaps, not only the last run. */
        if(kind==1) {
            long double ref=0;
            for(size_t i=0;i<n;i++) ref+=(long double)x[i]*y[i];
            double e=fabs((double)((long double)sink-ref)); if(e>max_error)max_error=e;
        } else {
            for(size_t i=0;i<span;i++) {
                double ref=initial_y(i);
                if(kind==0 && i%stride==0 && i/stride<n) ref+=0.5*(double)x[i]*inner;
                else if(kind==2 && i<n) ref=0.25*(double)x[i]+0.5*(double)x[i+1]+0.25*(double)x[i+2];
                else if(kind==3 && i<n) ref=x[i];
                double e=fabs((double)y[i]-ref);if(e>max_error)max_error=e;
            }
        }
        for(size_t i=0;i<offset;i++) if(xb[i]!=99 || yb[i]!=99)guards_ok=0;
        for(size_t i=offset+span;i<count;i++) if(xb[i]!=99 || yb[i]!=99)guards_ok=0;
    }
    printf("{\"kernel\":\"%s\",\"n\":%zu,\"inner\":%zu,\"stride\":%zu,\"offset\":%zu,\"itemsize\":%zu,\"x_mod64\":%zu,\"y_mod64\":%zu,\"max_error\":%.17g,\"guards_ok\":%d,\"counter_errno\":%d,\"samples\":[",argv[1],n,inner,stride,offset,sizeof(real),(size_t)((uintptr_t)x%64),(size_t)((uintptr_t)y%64),max_error,guards_ok,counter_errno);
    for(size_t i=0;i<repeats;i++)printf("%s{\"seconds\":%.17g,\"tsc_ticks_per_element\":%.17g,\"core_cycles_per_element\":%.17g}",i?",":"",seconds[i],tsc[i],cycles[i]);
    puts("]}");
    if(fd>=0)close(fd);
    free(xb);
    free(yb);
    return max_error>1e-5 || !guards_ok ? 1:0;
}
