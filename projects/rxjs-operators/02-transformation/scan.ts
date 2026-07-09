// 02-transformation/scan.ts
// Cumulative aggregation of emitted values
//
// pnpm exec ts-node 02-transformation\scan.ts

import { of, scan } from "rxjs";

of(1, 2, 3).pipe(scan((a, b) => a + b, 0)).subscribe(console.log)