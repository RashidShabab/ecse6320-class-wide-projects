CC      ?= gcc
CFLAGS  ?= -O2 -march=native -Wall -Wextra
BWFLAGS ?= -O3 -march=native -pthread -Wall -Wextra

all: pchase bwbench saxpy

src/chase_kernels.h: scripts/gen_kernels.py
	python3 scripts/gen_kernels.py

pchase: src/pchase.c src/chase_kernels.h
	$(CC) $(CFLAGS) -o $@ src/pchase.c

bwbench: src/bwbench.c
	$(CC) $(BWFLAGS) -o $@ src/bwbench.c

saxpy: src/saxpy.c
	$(CC) -O3 -march=native -Wall -Wextra -o $@ src/saxpy.c -lm

# Disassembly check: the 1-chain inner loop must be a bare `mov (%rax),%rax`
check-asm: pchase
	objdump -d pchase | awk '/<chase_1>:/,/ret/'

clean:
	rm -f pchase bwbench saxpy

.PHONY: all clean check-asm
