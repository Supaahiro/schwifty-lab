// 05-flattening/concat-map.ts
// Flattens and maps values from an Observable into inner Observables in sequence
//
// pnpm exec ts-node 05-flattening/concat-map.ts

import { concatMap, interval, map, of, take } from "rxjs";

of('A', 'B').pipe(
  concatMap(ch => interval(300).pipe(take(2), map(i => ch + i)))
).subscribe(console.log);