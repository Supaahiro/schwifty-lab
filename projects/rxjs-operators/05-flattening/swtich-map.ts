// 05-flattening/switch-map.ts
// Flattens and maps values from an Observable into inner Observables, switching to the latest
//
// pnpm exec ts-node 05-flattening/switch-map.ts

import { interval, map, switchMap, take } from "rxjs";

interval(1000).pipe(
  take(3),
  switchMap(i => interval(300).pipe(take(2), map(x => `Outer${i}-Inner${x}`)))
).subscribe(console.log);
