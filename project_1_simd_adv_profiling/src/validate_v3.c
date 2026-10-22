#include "kernels_v3.h"
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <stdint.h>
#include <string.h>

static uint32_t state=6320;
static real sample(void) {
    state=1664525*state+1013904223;
    return (real)((int)(state%2049)-1024)/(real)1024;
}
static void check(double actual,double ref,double scale) {
    double tol=sizeof(real)==4?2e-5:1e-12;
    if(!isfinite(actual) || fabs(actual-ref)>tol*(1+scale)) {
        fprintf(stderr,"mismatch %.17g vs %.17g\n",actual,ref);exit(1);
    }
}
int main(void) {
    size_t sizes[]={0,1,2,3,4,7,8,9,15,16,17,63,64,65,4097};
    for(size_t q=0;q<sizeof sizes/sizeof sizes[0];q++) {
        size_t n=sizes[q];
        for(size_t offset=0;offset<2;offset++) {
            for(size_t stride=1;stride<=8;stride*=2) {
                size_t count=n*stride+2;
                real *xb=malloc((count+offset)*sizeof(real)),*yb=malloc((count+offset)*sizeof(real));
                real *x=xb+offset,*y=yb+offset,*ref=malloc(count*sizeof(real));
                for(size_t i=0;i<count;i++){x[i]=sample();y[i]=sample();ref[i]=y[i];}
                for(size_t i=0;i<n;i++)ref[i*stride]=(real)0.5*x[i*stride]+ref[i*stride];
                saxpy_v3(x,y,n,stride);
                for(size_t i=0;i<count;i++)check(y[i],ref[i],fabs(ref[i]));
                if(stride==1) {
                    long double sum=0,abs_sum=0;
                    for(size_t i=0;i<n;i++){sum+=(long double)x[i]*y[i];abs_sum+=fabsl((long double)x[i]*y[i]);}
                    check(dot_v3(x,y,n),(double)sum,(double)abs_sum);
                    for(size_t i=0;i<n;i++)ref[i]=(real)(0.25*(double)x[i]+0.5*(double)x[i+1]+0.25*(double)x[i+2]);
                    stencil_v3(x,y,n);
                    for(size_t i=0;i<count;i++)check(y[i],ref[i],fabs(ref[i]));
                    copy_v3(x,y,n);
                    for(size_t i=0;i<n;i++)check(y[i],x[i],fabs(x[i]));
                }
                free(xb);free(yb);free(ref);
            }
        }
    }
    puts("PASS: reference validation, sizes 0..4097, strides 1/2/4/8, two offsets");
}
