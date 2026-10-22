Pitfall demos (session 20261022_165421; median of 5 reps)

| Point | Pages requested | AnonHugePages (kB) | ns/access | cycles/access | dTLB misses/access |
|---|---|---|---|---|---|
| chase_1G_rand | huge | 1048576 | 99.05 | 566.0 | 0.000 |
| chase_1G_seq | huge | 1048576 | 1.22 | 5.3 | 0.000 |
| tlb_512M_page4k | 4k | 0 | 106.59 | 607.6 | 0.909 |
| tlb_512M_pagedefault | thp | 524288 | 98.82 | 560.5 | 0.000 |
