// 05-flattening/merge-map.ts
// Flattens and maps values from an Observable into inner Observables
//
// pnpm exec ts-node 05-flattening/merge-map.ts

import { interval, map, mergeMap, of, take } from "rxjs";

of('x', 'y').pipe(
  mergeMap(ch => interval(500).pipe(take(2), map(i => ch + i)))
).subscribe(console.log);